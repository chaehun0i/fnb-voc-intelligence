"""Tenant·매장 범위를 검사하는 읽기 전용 사용 기록 Query입니다."""
import psycopg

from src.application.incidents.service import IncidentNotFound
from src.application.ports.llm_call_repository import LLMCallsUnavailable
from src.application.security.authorization import require


class LLMCallQueries:
    def __init__(self, persistence, principal):
        self.persistence, self.principal = persistence, principal

    def history(self, incident_id, limit=20):
        require(self.principal, "read")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("조회 개수는 1~100이어야 합니다.")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    raise IncidentNotFound(incident_id)
                require(self.principal, "read", incident.store)
                return uow.llm_calls.history(incident_id, limit)
        except (psycopg.Error, KeyError, ValueError, TypeError) as error:
            raise LLMCallsUnavailable() from error
