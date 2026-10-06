"""ai/ax/service: 통합된 기능 책임, 기존 실행 계약 유지."""
import psycopg

from src.application.incidents.service import IncidentNotFound
from src.application.ports.repositories import AgentRunsUnavailable
from src.application.security.authorization import require


def projection(run):
    state = run.state
    return {**run.model_dump(mode="json", exclude={"tenant_id", "state", "requested_by",
            "delegated_roles", "delegated_store_scope", "initial_incident_version"}),
        "route": state.route, "risk_level": state.risk_level,
        "findings": [f.model_dump() for f in state.findings],
        "evidence_candidates": [e.model_dump(mode="json", exclude={"tenant_id", "store"}) for e in state.evidence_candidates],
        "normalized_evidence": [e.model_dump(mode="json", exclude={"tenant_id", "store"}) for e in state.normalized_evidence],
        "sufficiency": state.sufficiency.model_dump(mode="json") if state.sufficiency else None,
        "rca_candidates": [c.model_dump(mode="json") for c in state.rca_candidates],
        "capa_proposals": [p.model_dump(mode="json", exclude={"tenant_id", "store"}) for p in state.capa_proposals],
        "approval": state.approval.model_dump(mode="json") if state.approval else None,
        "execution": state.execution.model_dump(mode="json", exclude={"tenant_id"}) if state.execution else None,
        "verification": state.verification.model_dump(mode="json") if state.verification else None,
        "verification_evidence": [e.model_dump(mode="json", exclude={"tenant_id", "store"}) for e in state.verification_evidence],
        "resulting_incident_status": state.resulting_incident_status,
        "evidence_gaps": [g.model_dump() for g in state.evidence_gaps],
        "token_spent": state.token_spent, "cost_spent": state.cost_spent,
        "iteration": state.iteration, "tool_call_count": state.tool_call_count}


class AgentRunQueries:
    def __init__(self, persistence, principal):
        self.persistence, self.principal = persistence, principal

    def execute(self, incident_id, *, run_id=None, limit=20, offset=0):
        require(self.principal, "read")
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise ValueError("실행 이력 조회 범위를 확인해 주세요.")
        try:
            with self.persistence.transaction(self.principal.tenant_id) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    raise IncidentNotFound()
                require(self.principal, "read", incident.store)
                if run_id is not None:
                    run = uow.agent_runs.get(run_id)
                    if run is None or run.incident_id != incident_id:
                        raise IncidentNotFound()
                    detail = projection(run)
                    if run.state.approval:
                        approval = uow.approvals.get(run.state.approval.approval_id)
                        if approval and approval.agent_run_id == run.agent_run_id:
                            detail["approval"].update(status=approval.status, decision_actor=approval.decided_by,
                                decision_reason_code="HUMAN_APPROVED" if approval.status == "APPROVED"
                                else "HUMAN_REJECTED" if approval.status == "REJECTED" else None)
                    return {**detail, "steps": [s.model_dump(mode="json", exclude={"result"})
                            for s in uow.agent_runs.steps(run_id)]}
                runs = uow.agent_runs.history(incident_id, limit+1, offset)
                return {"runs": [projection(r) for r in runs[:limit]], "limit": limit,
                        "offset": offset, "has_more": len(runs)>limit}
        except psycopg.Error as error:
            raise AgentRunsUnavailable() from error
