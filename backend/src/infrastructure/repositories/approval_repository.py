"""메모리 예시와 PostgreSQL의 조직별 승인 저장소입니다."""

from copy import deepcopy
from dataclasses import asdict, replace
from threading import RLock

from psycopg.types.json import Jsonb

from src.application.ports.incident_repository import IncidentConflict
from src.domain.approvals.models import Approval


class MemoryAccessState:
    def __init__(self):
        self.lock = RLock()
        self.data = {"approvals": {}}


class MemoryApprovalRepository:
    def __init__(self, state: MemoryAccessState, tenant_id: str):
        self.state, self.tenant_id = state, tenant_id

    def get(self, approval_id):
        with self.state.lock:
            item = self.state.data["approvals"].get(approval_id)
            return deepcopy(item) if item and item.tenant_id == self.tenant_id else None

    def list(self, incident_id=None):
        with self.state.lock:
            items = [item for item in self.state.data["approvals"].values()
                     if item.tenant_id == self.tenant_id
                     and (incident_id is None or item.incident_id == incident_id)]
            return deepcopy(sorted(items, key=lambda item: (
                item.requested_at, item.incident_version), reverse=True))

    def save(self, approval):
        with self.state.lock:
            if approval.tenant_id != self.tenant_id:
                raise IncidentConflict()
            previous = self.state.data["approvals"].get(approval.approval_id)
            if approval.agent_run_id and any(a.tenant_id == self.tenant_id and a.agent_run_id == approval.agent_run_id
                    and a.approval_id != approval.approval_id for a in self.state.data["approvals"].values()):
                raise IncidentConflict()
            if previous and (previous.tenant_id != self.tenant_id
                             or previous.version != approval.version
                             or previous.status != "PENDING"):
                raise IncidentConflict()
            saved = replace(approval, version=approval.version + 1) if previous else approval
            self.state.data["approvals"][saved.approval_id] = deepcopy(saved)
            return deepcopy(saved)


class PostgresApprovalRepository:
    def __init__(self, connection, tenant_id: str):
        self.connection, self.tenant_id = connection, tenant_id

    def get(self, approval_id):
        row = self.connection.execute(
            "SELECT document FROM serviq_approvals WHERE tenant_id=%s AND approval_id::text=%s",
            (self.tenant_id, approval_id),
        ).fetchone()
        return Approval(**row[0]) if row else None

    def list(self, incident_id=None):
        rows = self.connection.execute(
            """SELECT document FROM serviq_approvals WHERE tenant_id=%s
            AND (%s::text IS NULL OR incident_id=%s)
            ORDER BY requested_at DESC, (document->>'incident_version')::int DESC""",
            (self.tenant_id, incident_id, incident_id),
        ).fetchall()
        return [Approval(**row[0]) for row in rows]

    def save(self, approval):
        if approval.tenant_id != self.tenant_id:
            raise IncidentConflict()
        previous = self.get(approval.approval_id)
        saved = replace(approval, version=approval.version+1) if previous else approval
        if previous:
            row = self.connection.execute(
                """UPDATE serviq_approvals SET version=%s,status=%s,document=%s
                WHERE tenant_id=%s AND approval_id=%s AND version=%s AND status='PENDING'
                RETURNING approval_id""",
                (saved.version, saved.status, Jsonb(asdict(saved)), self.tenant_id,
                 saved.approval_id, approval.version),
            ).fetchone()
        else:
            row = self.connection.execute(
                """INSERT INTO serviq_approvals(approval_id,tenant_id,incident_id,
                version,status,requested_at,document,agent_run_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING approval_id""",
                (saved.approval_id, self.tenant_id, saved.incident_id, saved.version,
                 saved.status, saved.requested_at, Jsonb(asdict(saved)), saved.agent_run_id),
            ).fetchone()
        if row is None:
            raise IncidentConflict()
        return saved
