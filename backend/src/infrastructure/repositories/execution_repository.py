"""UoW의 같은 연결에서 실행/검증 출처를 immutable insert합니다."""
from psycopg.types.json import Jsonb

from src.application.ports.incident_repository import IncidentConflict
from src.domain.workflows.verification import (
    ActionExecutionRecord,
    VerificationEvidence,
)


class ExecutionRepository:
    def __init__(self, uow, memory, tenant_id):
        self.uow, self.memory, self.tenant_id = uow, memory, tenant_id

    def get(self, run_id):
        if self.uow.connection:
            row = self.uow.connection.execute("SELECT document FROM serviq_internal_executions WHERE tenant_id=%s AND agent_run_id=%s",
                (self.tenant_id, run_id)).fetchone()
            return ActionExecutionRecord.model_validate(row[0]) if row else None
        return self.memory.data.get("internal_executions", {}).get((self.tenant_id, run_id))

    def append(self, record):
        ActionExecutionRecord.model_validate(record.model_dump(mode="json"))
        if record.tenant_id != self.tenant_id or self.uow.agent_runs.get(record.agent_run_id) is None:
            raise IncidentConflict()
        previous = self.get(record.agent_run_id)
        if previous:
            if previous != record:
                raise IncidentConflict()
            return previous
        if self.uow.connection:
            self.uow.connection.execute("INSERT INTO serviq_internal_executions(tenant_id,agent_run_id,execution_id,document) VALUES(%s,%s,%s,%s)",
                (self.tenant_id, record.agent_run_id, record.execution_id, Jsonb(record.model_dump(mode="json"))))
        else:
            self.memory.data.setdefault("internal_executions", {})[(self.tenant_id, record.agent_run_id)] = record
        return record

    def evidence(self, execution):
        if self.uow.connection:
            rows = self.uow.connection.execute("SELECT document FROM serviq_verification_evidence WHERE tenant_id=%s AND execution_id=%s ORDER BY evidence_id LIMIT 20",
                (self.tenant_id, execution.execution_id)).fetchall()
            return tuple(VerificationEvidence.model_validate(r[0]) for r in rows)
        return tuple(sorted((e for (t, _), e in self.memory.data.get("verification_evidence", {}).items()
            if t == self.tenant_id and e.execution_id == execution.execution_id), key=lambda e: e.evidence_id))

    def append_evidence(self, execution, evidence):
        VerificationEvidence.model_validate(evidence.model_dump(mode="json"))
        if (evidence.tenant_id != self.tenant_id or evidence.agent_run_id != execution.agent_run_id
                or evidence.action_id != execution.action_id or evidence.execution_id != execution.execution_id):
            raise IncidentConflict()
        previous = next((e for e in self.evidence(execution) if e.evidence_id == evidence.evidence_id), None)
        if previous:
            if previous != evidence:
                raise IncidentConflict()
            return previous
        if len(self.evidence(execution)) >= 20:
            raise IncidentConflict()
        if self.uow.connection:
            self.uow.connection.execute("INSERT INTO serviq_verification_evidence(tenant_id,execution_id,evidence_id,document) VALUES(%s,%s,%s,%s)",
                (self.tenant_id, execution.execution_id, evidence.evidence_id, Jsonb(evidence.model_dump(mode="json"))))
        else:
            self.memory.data.setdefault("verification_evidence", {})[(self.tenant_id, evidence.evidence_id)] = evidence
