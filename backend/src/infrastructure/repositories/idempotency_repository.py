"""DB 유일성과 업무 트랜잭션으로 중복 실행을 차단합니다."""
from copy import deepcopy

from psycopg.types.json import Jsonb

from src.ai.workflow.models import RuntimeEvent
from src.application.security.principal import AccessError
from src.domain.config.models import (
    ConfigVersion,
    version_document,
    version_from_document,
)
from src.domain.jobs.models import Job
from src.infrastructure.incident_codec import incident_document, incident_from_document
from src.infrastructure.job_codec import job_document, job_from_document


def result_document(result):
    if isinstance(result, RuntimeEvent):
        return {"resource_type": "agent_control", "document": result.model_dump(mode="json")}
    if isinstance(result, ConfigVersion):
        return {"resource_type": "runtime_config", "document": version_document(result)}
    return {"resource_type": "job", "document": job_document(result)} if isinstance(result, Job) else incident_document(result)


def replay(record, fingerprint):
    if record[0] != fingerprint:
        raise AccessError("IDEMPOTENCY_CONFLICT", 409)
    if record[1] is None:
        raise AccessError("PROCESSING", 409)
    if record[1].get("resource_type") == "job":
        return job_from_document(record[1]["document"])
    if record[1].get("resource_type") == "runtime_config":
        return version_from_document(record[1]["document"])
    if record[1].get("resource_type") == "agent_control":
        return RuntimeEvent.model_validate(record[1]["document"])
    return incident_from_document(record[1])


class MemoryIdempotencyRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def claim(self, principal_id, operation, key, fingerprint):
        scope = (self.tenant_id, principal_id, operation, key)
        records = self.state.data.setdefault("idempotency", {})
        if scope in records:
            return replay(records[scope], fingerprint)
        records[scope] = (fingerprint, None)
        return None

    def complete(self, principal_id, operation, key, result):
        scope = (self.tenant_id, principal_id, operation, key)
        records = self.state.data["idempotency"]
        records[scope] = (records[scope][0], deepcopy(result_document(result)))


class PostgresIdempotencyRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def claim(self, principal_id, operation, key, fingerprint):
        scope = (self.tenant_id, principal_id, operation, key)
        row = self.connection.execute(
            """INSERT INTO serviq_idempotency(tenant_id,principal_id,operation,key,fingerprint)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING key""",
            (*scope, fingerprint),
        ).fetchone()
        if row:
            return None
        record = self.connection.execute(
            """SELECT fingerprint,result FROM serviq_idempotency
            WHERE tenant_id=%s AND principal_id=%s AND operation=%s AND key=%s""", scope,
        ).fetchone()
        return replay(record, fingerprint)

    def complete(self, principal_id, operation, key, result):
        self.connection.execute(
            """UPDATE serviq_idempotency SET status='COMPLETED',result=%s
            WHERE tenant_id=%s AND principal_id=%s AND operation=%s AND key=%s""",
            (Jsonb(result_document(result)), self.tenant_id, principal_id, operation, key),
        )
