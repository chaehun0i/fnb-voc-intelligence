"""판단 조회는 기존 Principal/Tenant/store 경계를 통과하는 읽기 전용 Query입니다."""
from dataclasses import asdict

import psycopg

from src.application.incidents.service import IncidentNotFound
from src.application.ports.decision_repository import DecisionsUnavailable
from src.application.security.authorization import require


def projection(record):
    document = asdict(record)
    document["decided_at"] = record.decided_at.isoformat()
    return {**document["result"], **{key: document[key] for key in (
        "decision_id", "incident_id", "source_job_id", "decided_at", "duration_ms", "incident_version", "error_code")}}


class DecisionQueries:
    def __init__(self, persistence, principal):
        self.persistence, self.principal = persistence, principal

    def history(self, incident_id, limit=20, offset=0):
        require(self.principal, "read")
        if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 10000:
            raise ValueError("판단 이력 조회 범위를 확인해 주세요.")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    raise IncidentNotFound()
                require(self.principal, "read", incident.store)
                records = uow.decisions.history(incident_id, limit+1, offset)
                return {"decisions": [projection(r) for r in records[:limit]], "limit": limit,
                        "offset": offset, "has_more": len(records) > limit}
        except psycopg.Error as error:
            raise DecisionsUnavailable() from error

    def latest(self, incident_id):
        return next(iter(self.history(incident_id, 1)["decisions"]), None)
