"""Agent 제안을 재검증한 뒤 기존 Incident Command로만 반영합니다."""
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.agents.models import ApprovalTrace, WorkflowState, WorkflowStatus
from src.agents.policy import server_risk
from src.application.approvals.service import ApprovalService
from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.incident_repository import IncidentConflict
from src.application.security.authorization import require
from src.application.security.principal import AccessError, Principal, RequestContext
from src.domain.approvals.audit import AuditRecord
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import CorrectiveAction, Evidence, RootCauseCandidate


class CAPACommands:
    def __init__(self, persistence, run_id, tenant_id, clock=None):
        self.persistence, self.run_id, self.tenant_id = persistence, run_id, tenant_id
        self.clock = clock or (lambda: datetime.now(UTC))

    def apply(self, state):
        WorkflowState.model_validate(state.model_dump(mode="json"))
        with self.persistence.transaction(self.tenant_id) as uow:
            run = uow.agent_runs.get(self.run_id)
            if run is None or not run.requested_by or state.agent_run_id != run.agent_run_id:
                raise AccessError()
            principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles),
                                  frozenset(run.delegated_store_scope), "workflow-delegation")
            incident = uow.incidents.get(run.incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            if run.state.capa_proposals and all(p.status == "APPLIED" for p in run.state.capa_proposals):
                return run.state
            version = uow.configs.get(run.config_version)
            if (version is None or not version.config.auto_capa_draft or not state.sufficiency
                    or not state.sufficiency.allows_rca or not state.capa_proposals):
                raise AccessError("CAPA_NOT_ALLOWED", 409)
            if incident.version != run.initial_incident_version:
                raise IncidentConflict()
            if state.rca_candidates != run.state.rca_candidates or state.normalized_evidence != run.state.normalized_evidence:
                raise AccessError("CAPA_LINEAGE_MISMATCH", 409)
            if any(p.store != incident.store or p.decision_reference != run.jev_decision_id
                   for p in state.capa_proposals) or any(e.store != incident.store for e in state.normalized_evidence):
                raise AccessError()
            service = IncidentService(uow.incidents, clock=self.clock, principal=principal)
            if incident.status == IncidentStatus.TRIAGED:
                incident = service.investigate(incident.id, incident.version)
            for e in state.normalized_evidence:
                incident = service.add_evidence(incident.id, Evidence(e.source_ref, e.source_ref,
                    e.source_type, "관련 과거 사례 참조", 1.0), incident.version)
            incident = service.prepare_rca(incident.id, [RootCauseCandidate(c.candidate_id,
                c.hypothesis, c.confidence, list(c.supporting_refs), list(c.contradicting_refs))
                for c in state.rca_candidates], incident.version)
            proposals = tuple(p.model_copy(update={"risk_level": server_risk(incident.severity,
                state.risk_level, p.risk_level), "required_approval": True, "status": "APPLIED"})
                for p in state.capa_proposals)
            incident = service.propose_action(incident.id, [CorrectiveAction(p.capa_proposal_id,
                p.summary, Severity(p.risk_level), p.expected_effect, p.verification_criteria,
                action_type=p.proposed_action_type, target_reference=p.target_reference)
                for p in proposals], incident.version)
            result = WorkflowState.model_validate(state.model_copy(update={"capa_proposals": proposals}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "capa:"+run.agent_run_id)),
                run.tenant_id, principal.principal_id, "workflow_capa", "incident", incident.id,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), incident.version))
            return result

    def request_approval(self, state):
        from src.agents.approval_policy import approval_policy_digest
        with self.persistence.transaction(self.tenant_id) as uow:
            run = uow.agent_runs.get(self.run_id)
            if run is None or not run.requested_by:
                raise AccessError()
            principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles),
                                  frozenset(run.delegated_store_scope), "workflow-delegation")
            incident = uow.incidents.get(run.incident_id)
            if incident is None:
                raise IncidentNotFound()
            require(principal, "operate", incident.store)
            if run.state.approval:
                return run.state
            if state != run.state or any(p.status != "APPLIED" for p in state.capa_proposals) or not state.capa_proposals:
                raise AccessError("CAPA_NOT_ALLOWED", 409)
            pinned, current = uow.configs.get(run.config_version), uow.configs.current()
            if pinned is None or current is None:
                raise IncidentConflict()
            policy = pinned.config
            if approval_policy_digest(policy) != approval_policy_digest(current.config):
                raise IncidentConflict()
            risk = server_risk(incident.severity, *(p.risk_level for p in state.capa_proposals))
            if any(server_risk(p.risk_level) != risk for p in state.capa_proposals):
                raise IncidentConflict()
            if risk == "CRITICAL" and policy.critical_approver_count != 1:
                raise AccessError("APPROVAL_POLICY_UNSUPPORTED", 409)
            aid = str(uuid5(NAMESPACE_URL, "workflow-approval:"+run.agent_run_id))
            service = IncidentService(uow.incidents, clock=self.clock, principal=principal)
            ApprovalService(service, uow.approvals, RequestContext(principal, run.agent_run_id,
                run.correlation_id)).request(incident.id, incident.version, approval_id=aid,
                workflow_metadata={"agent_run_id": run.agent_run_id, "config_version": run.config_version,
                    "policy_digest": approval_policy_digest(policy), "required_roles": policy.required_roles,
                    "separation_of_duties": policy.separation_of_duties})
            approval = uow.approvals.get(aid)
            trace = ApprovalTrace(approval_id=aid, action_ids=approval.action_ids,
                action_digest=approval.action_digest, config_version=run.config_version,
                incident_version=approval.incident_version, waiting_since=self.clock())
            result = WorkflowState.model_validate(state.model_copy(update={"approval": trace}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "approval-request:"+run.agent_run_id)),
                run.tenant_id, principal.principal_id, "workflow_approval_request", "approval", aid,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), approval.version))
            return result

    def approval_result(self, state):
        from src.agents.resume import validate_approval
        with self.persistence.transaction(self.tenant_id) as uow:
            existing = uow.agent_runs.get(self.run_id)
            if existing and existing.state.execution and state.approval and existing.state.approval.approval_id == state.approval.approval_id:
                return existing.state
            if state.approval is None:
                raise IncidentConflict()
            approval = uow.approvals.get(state.approval.approval_id)
            if approval is None:
                raise IncidentConflict()
            run, _ = validate_approval(uow, approval, self.clock(), decided=True)
            if run.agent_run_id != self.run_id:
                raise AccessError()
            trace = state.approval.model_copy(update={"status": approval.status,
                "phase": "READY_TO_EXECUTE" if approval.status == "APPROVED" else "REJECTED",
                "resumed_at": self.clock(), "decision_actor": approval.decided_by,
                "decision_reason_code": "HUMAN_APPROVED" if approval.status == "APPROVED" else "HUMAN_REJECTED"})
            result = WorkflowState.model_validate(state.model_copy(update={"approval": trace,
                "status": WorkflowStatus.RUNNING}).model_dump(mode="json"))
            uow.agent_runs.save(run.model_copy(update={"state": result, "status": WorkflowStatus.RUNNING}))
            uow.audit.append(AuditRecord(str(uuid5(NAMESPACE_URL, "approval-resumed:"+run.agent_run_id)),
                run.tenant_id, approval.decided_by, "workflow_resume", "agent_run", run.agent_run_id,
                "SUCCESS", run.agent_run_id, run.correlation_id, self.clock().isoformat(), approval.version))
            return result
