"""내부 기록/검증은 Graph가 아닌 인증된 Application Command로 적용합니다."""
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.incident_repository import IncidentConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError, Principal
from src.application.workflows.approval_policy import approval_policy_digest
from src.application.workflows.resume import validate_approval
from src.domain.approvals.audit import AuditRecord
from src.domain.approvals.models import action_digest
from src.domain.workflows.models import WorkflowState
from src.domain.workflows.verification import ActionExecutionRecord
from src.domain.workflows.verification_rules import evaluate_verification


class VerificationCommands:
    def __init__(self, persistence, run_id, tenant_id, clock=None):
        self.persistence, self.run_id, self.tenant_id = persistence, run_id, tenant_id
        self.clock = clock or (lambda: datetime.now(UTC))

    def load(self, uow):
        run = uow.agent_runs.get(self.run_id)
        if run is None or not run.requested_by:
            raise AccessError()
        incident = uow.incidents.get(run.incident_id)
        if incident is None:
            raise IncidentNotFound()
        principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles),
            frozenset(run.delegated_store_scope), "workflow-delegation")
        require(principal, "operate", incident.store)
        return run, incident, principal

    def audit(self, uow, run, principal, operation, version):
        uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, operation+":"+run.agent_run_id)),
            run.tenant_id, principal.principal_id, operation, "incident", run.incident_id,
            "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), version))

    def execute(self, state):
        WorkflowState.model_validate(state.model_dump(mode="json"))
        with self.persistence.transaction(self.tenant_id) as uow:
            run, incident, principal = self.load(uow)
            repo = uow.executions
            existing = repo.get(run.agent_run_id)
            if existing:
                if state.execution and state.execution != existing:
                    raise IncidentConflict()
                return run.state
            pinned, current = uow.configs.get(run.config_version), uow.configs.current()
            if (run.workflow_version != "history-verification-v4" or pinned is None or current is None
                    or not pinned.config.internal_execution_enabled or not current.config.internal_execution_enabled
                    or state != run.state or not state.approval or state.approval.phase != "READY_TO_EXECUTE"
                    or len(state.capa_proposals) != 1):
                raise AccessError("INTERNAL_EXECUTION_NOT_ALLOWED", 409)
            approval = uow.approvals.get(state.approval.approval_id)
            if approval is None or approval.status != "APPROVED":
                raise IncidentConflict()
            validate_approval(uow, approval, self.clock(), decided=True)
            if not incident.corrective_actions[0].verification_criteria.strip():
                raise IncidentConflict()
            saved = IncidentService(uow.incidents, clock=self.clock, principal=principal).start_internal_execution(
                incident.id, state.approval.incident_version+1)
            record = repo.append(ActionExecutionRecord(execution_id=str(uuid5(NAMESPACE_URL, "internal-execution:"+run.agent_run_id)),
                tenant_id=run.tenant_id, incident_id=incident.id, agent_run_id=run.agent_run_id,
                action_id=incident.corrective_actions[0].id, approval_id=approval.approval_id,
                action_digest=approval.action_digest, started_at=self.clock(), completed_at=self.clock(),
                config_version=run.config_version, correlation_id=run.correlation_id, incident_version=saved.version))
            result = WorkflowState.model_validate(run.state.model_copy(update={"execution": record,
                "resulting_incident_status": "EXECUTING"}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            self.audit(uow, run, principal, "internal_execution_recorded", saved.version)
            return result

    def begin_verification(self, state):
        with self.persistence.transaction(self.tenant_id) as uow:
            run, incident, principal = self.load(uow)
            record = uow.executions.get(run.agent_run_id)
            if record is None or state.execution != record or run.state.execution != record:
                raise IncidentConflict()
            if run.state.resulting_incident_status in {"VERIFYING", "RESOLVED", "REOPENED"}:
                return run.state
            approval = uow.approvals.get(record.approval_id)
            current = uow.configs.current()
            if (approval is None or approval.status != "APPROVED" or current is None
                    or not current.config.internal_execution_enabled
                    or approval.policy_digest != approval_policy_digest(current.config)
                    or self.clock() >= datetime.fromisoformat(approval.expires_at)
                    or action_digest(incident) != record.action_digest
                    or incident.version != record.incident_version or incident.status != "EXECUTING"):
                raise IncidentConflict()
            saved = IncidentService(uow.incidents, clock=self.clock, principal=principal).start_internal_verification(
                incident.id, record.incident_version)
            result = run.state.model_copy(update={"resulting_incident_status": "VERIFYING"})
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            self.audit(uow, run, principal, "internal_verification_started", saved.version)
            return result

    def record_evidence(self, context, evidence, expected_version):
        """공개 Agent 실행 API가 아닌 좁은 인증된 내부 source ingest 경계입니다."""
        if context.principal.tenant_id != self.tenant_id:
            raise AccessError()
        with self.persistence.transaction(self.tenant_id) as uow:
            run, incident, _ = self.load(uow)
            require(context.principal, "operate", incident.store)
            record = uow.executions.get(run.agent_run_id)
            if (record is None or incident.status != "VERIFYING" or incident.version != expected_version
                    or run.state.verification is not None or evidence.store != incident.store
                    or evidence.observed_at < record.completed_at or evidence.observed_at > self.clock()
                    or not set(evidence.additional_evidence_refs) <= {e.source_ref for e in run.state.normalized_evidence}):
                raise IncidentConflict()
            return uow.executions.append_evidence(record, evidence)

    def evaluate(self, state):
        with self.persistence.transaction(self.tenant_id) as uow:
            run, _, _ = self.load(uow)
            if run.state.verification:
                return run.state
            if state != run.state or not state.execution:
                raise IncidentConflict()
            evidence = uow.executions.evidence(state.execution)
            pinned = uow.configs.get(run.config_version)
            if pinned is None:
                raise IncidentConflict()
            result = evaluate_verification(state.model_copy(update={"verification_evidence": evidence}),
                self.clock(), window_hours=pinned.config.verification_window_hours)
            # 후보를 저장하지 않고 다음 Command에서 저장 원본과 함께 재검증합니다.
            return result

    def apply(self, state):
        with self.persistence.transaction(self.tenant_id) as uow:
            run, incident, principal = self.load(uow)
            if run.state.verification:
                if state.verification != run.state.verification:
                    raise IncidentConflict()
                return run.state
            record = uow.executions.get(run.agent_run_id)
            evidence = uow.executions.evidence(record) if record else ()
            pinned = uow.configs.get(run.config_version)
            if (record is None or pinned is None or run.state.execution != record
                    or incident.status != "VERIFYING" or incident.version != record.incident_version+1
                    or action_digest(incident) != record.action_digest or state.execution != record
                    or state.verification_evidence != evidence or state.verification is None):
                raise IncidentConflict()
            regenerated = evaluate_verification(run.state.model_copy(update={"verification_evidence": evidence}),
                state.verification.verified_at, window_hours=pinned.config.verification_window_hours)
            if (regenerated.verification != state.verification or state.verification.verified_at > self.clock()
                    or state.verification.verified_at < record.completed_at):
                raise IncidentConflict()
            candidate = state.verification
            saved = IncidentService(uow.incidents, clock=self.clock, principal=principal).verify(
                incident.id, candidate.result, candidate.summary, incident.version,
                verification_id=candidate.verification_id, execution_id=record.execution_id,
                evidence_refs=candidate.evidence_ids, criteria=candidate.criteria,
                observation_mode=candidate.observation_mode)
            result = WorkflowState.model_validate(state.model_copy(update={
                "resulting_incident_status": saved.status}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            self.audit(uow, run, principal, "verification_"+candidate.result.lower(), saved.version)
            return result
