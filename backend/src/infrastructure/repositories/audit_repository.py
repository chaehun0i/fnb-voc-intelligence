"""민감한 요청 본문 없이 실행 주체와 결과만 저장합니다."""
from copy import deepcopy
from dataclasses import asdict

from psycopg.types.json import Jsonb

from src.application.security.principal import AccessError
from src.domain.approvals.audit import AuditRecord


class MemoryAuditRepository:
    def __init__(self, state, tenant_id):
        self.state, self.tenant_id = state, tenant_id

    def append(self, record):
        if record.tenant_id != self.tenant_id:
            raise AccessError()
        self.state.data.setdefault("audit", []).append(record)

    def list(self):
        return deepcopy([item for item in self.state.data.get("audit", [])
                         if item.tenant_id == self.tenant_id])


class PostgresAuditRepository:
    def __init__(self, connection, tenant_id):
        self.connection, self.tenant_id = connection, tenant_id

    def append(self, record):
        if record.tenant_id != self.tenant_id:
            raise AccessError()
        self.connection.execute(
            "INSERT INTO serviq_audit(audit_id,tenant_id,occurred_at,document) VALUES(%s,%s,%s,%s)",
            (record.audit_id, self.tenant_id, record.occurred_at, Jsonb(asdict(record))),
        )

    def list(self):
        rows = self.connection.execute(
            "SELECT document FROM serviq_audit WHERE tenant_id=%s ORDER BY occurred_at,audit_id",
            (self.tenant_id,),
        ).fetchall()
        return [AuditRecord(**row[0]) for row in rows]
