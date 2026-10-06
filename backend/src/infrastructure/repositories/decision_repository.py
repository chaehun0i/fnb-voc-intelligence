"""판단 감사는 원문 없이 append-only로 저장하며 조직 범위를 생략하지 않습니다."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime

from psycopg.types.json import Jsonb

from src.ai.decision.models import (
    AgentType,
    DecisionReasonCode,
    DecisionRecord,
    DecisionResult,
    DecisionRoute,
)
from src.application.security.principal import AccessError
from src.domain.incidents.enums import Priority, Severity


def decision_document(record):
    return {**asdict(record), "decided_at": record.decided_at.isoformat()}


def decision_from_document(document):
    result = document["result"]
    return DecisionRecord(**{**document, "decided_at": datetime.fromisoformat(document["decided_at"]),
        "result": DecisionResult(**{**result, "route": DecisionRoute(result["route"]),
            "risk_level": Severity(result["risk_level"]), "priority": Priority(result["priority"]),
            "investigation_agents": tuple(AgentType(x) for x in result["investigation_agents"]),
            "reason_codes": tuple(DecisionReasonCode(x) for x in result["reason_codes"])})})


def validate_record(record, tenant_id):
    if record.tenant_id != tenant_id:
        raise AccessError()
    if record.result.mode != "SHADOW" or record.decided_at.tzinfo is None or record.duration_ms < 0:
        raise ValueError("판단 감사의 모드·시각·소요 시간을 확인해 주세요.")


class MemoryDecisionRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def history(self, incident_id, limit=20, offset=0):
        items = [r for r in self.state.data.get("decisions", {}).values()
                 if r.tenant_id == self.tenant_id and r.incident_id == incident_id]
        return deepcopy(sorted(items, key=lambda r: (r.decided_at, r.decision_id), reverse=True)[offset:offset+limit])

    def get(self, decision_id):
        return deepcopy(next((r for r in self.state.data.get("decisions", {}).values()
                              if r.tenant_id == self.tenant_id and r.decision_id == decision_id), None))

    def by_job(self, job_id, ruleset="1"):
        return deepcopy(self.state.data.get("decisions", {}).get((self.tenant_id, job_id, ruleset)))

    def append(self, record):
        validate_record(record, self.tenant_id)
        key = (self.tenant_id, record.source_job_id, record.result.ruleset_version)
        self.state.data.setdefault("decisions", {}).setdefault(key, deepcopy(record))
        return deepcopy(self.state.data["decisions"][key])


class PostgresDecisionRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def history(self, incident_id, limit=20, offset=0):
        rows = self.connection.execute("""SELECT document FROM serviq_decisions WHERE tenant_id=%s AND incident_id=%s
            ORDER BY decided_at DESC,decision_id DESC LIMIT %s OFFSET %s""", (self.tenant_id, incident_id, limit, offset)).fetchall()
        return [decision_from_document(r[0]) for r in rows]

    def get(self, decision_id):
        row = self.connection.execute("SELECT document FROM serviq_decisions WHERE tenant_id=%s AND decision_id::text=%s",
                                      (self.tenant_id, decision_id)).fetchone()
        return decision_from_document(row[0]) if row else None

    def by_job(self, job_id, ruleset="1"):
        row = self.connection.execute("SELECT document FROM serviq_decisions WHERE tenant_id=%s AND source_job_id=%s AND ruleset_version=%s",
                                      (self.tenant_id, job_id, ruleset)).fetchone()
        return decision_from_document(row[0]) if row else None

    def append(self, record):
        validate_record(record, self.tenant_id)
        self.connection.execute("""INSERT INTO serviq_decisions(decision_id,tenant_id,incident_id,source_job_id,
            ruleset_version,config_version,mode,input_digest,decided_at,document)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(tenant_id,source_job_id,ruleset_version) DO NOTHING""",
            (record.decision_id, self.tenant_id, record.incident_id, record.source_job_id,
             record.result.ruleset_version, record.result.config_version, record.result.mode,
             record.input_digest, record.decided_at, Jsonb(decision_document(record))))
        return self.by_job(record.source_job_id, record.result.ruleset_version)
