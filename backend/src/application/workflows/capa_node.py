"""CAPA는 제한된 제안만 반환하며 업무 저장/승인을 수행하지 않습니다."""
from uuid import NAMESPACE_URL, uuid5

from src.domain.workflows.models import CAPAProposal, WorkflowState
from src.domain.workflows.policy import server_risk


class CAPAInvestigation:
    def __init__(self, resolved, decision_id, *, store, incident_severity):
        self.resolved, self.decision_id = resolved, decision_id
        self.store, self.incident_severity = store, incident_severity

    def __call__(self, state):
        state = WorkflowState.model_validate(state.model_dump(mode="json"))
        if state.capa_proposals and all(p.status == "APPLIED" for p in state.capa_proposals):
            # checkpoint 재시도는 Application에 반영된 조치와 Approval lineage를 보존합니다.
            return state
        if (not self.resolved.effective.auto_capa_draft or state.sufficiency is None
                or not state.sufficiency.allows_rca or not state.rca_candidates):
            return state
        risk = server_risk(state.risk_level, self.incident_severity)
        proposals = tuple(CAPAProposal(
            capa_proposal_id=str(uuid5(NAMESPACE_URL, "capa:"+state.agent_run_id+":"+c.candidate_id)),
            tenant_id=state.tenant_id, store=self.store, incident_id=state.incident_id,
            agent_run_id=state.agent_run_id, rca_candidate_id=c.candidate_id,
            risk_level=risk, supporting_evidence_ids=c.supporting_refs,
            target_reference=state.incident_id, config_version=state.config_version,
            decision_reference=self.decision_id) for c in sorted(state.rca_candidates, key=lambda c: c.candidate_id)[:3])
        return WorkflowState.model_validate(state.model_copy(update={"capa_proposals": proposals}).model_dump(mode="json"))
