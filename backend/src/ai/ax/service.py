"""ai/ax/service: 통합된 기능 책임, 기존 실행 계약 유지."""
import psycopg

from src.ai.ax.actions import next_action
from src.ai.ax.explanations import explain
from src.ai.ax.models import AgentControlView
from src.ai.ax.projector import project_incident
from src.ai.workflow.controller import control_state
from src.ai.workflow.policy import AGENT_REGISTRY
from src.application.approvals.queries import ReviewQueries
from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.ports.repositories import AgentRunsUnavailable
from src.application.security.authorization import allowed, require


def investigation_projection(run, branches=None):
    state = run.state
    if state.selection is None:
        return None
    results = {b.agent_type: b for b in (branches if branches is not None else state.branches)}
    selected = {a.agent_type for a in state.selection.selected}
    progress, coverage = [], []
    for a in AGENT_REGISTRY:
        if a.agent_type not in selected and a.agent_type not in state.selection.excluded:
            continue
        result = results.get(a.agent_type)
        status = result.status if result else ("FAILED" if run.status == "FAILED" else "RUNNING") if a.agent_type in selected else "UNAVAILABLE"
        count = len({e.source_ref for e in result.evidence_candidates}) if result else 0
        coverage_status = "CONFLICTING" if result and any(e.stance == "CONTRADICTING" for e in result.evidence_candidates) else (
            "CONFIRMED" if count else "STALE" if status == "STALE" else "MISSING")
        progress.append({"agent_type": a.agent_type, "business_label": a.business_label,
            "status": status, "evidence_count": count, "retryable": result.retryable if result else False,
            "gap_codes": [g.code for g in result.evidence_gaps] if result else
                ["CAPABILITY_UNAVAILABLE"] if status == "UNAVAILABLE" else [],
            "updated_at": (result.completed_at if result else run.started_at).isoformat()})
        coverage.append({"dimension": a.agent_type, "status": coverage_status})
    pending = any(p["status"] == "RUNNING" for p in progress)
    partial = any(p["status"] in {"FAILED", "UNAVAILABLE", "STALE", "NO_EVIDENCE"} for p in progress)
    refs = {e.source_ref for b in results.values() for e in b.evidence_candidates}
    return {"status": "RUNNING" if pending else "PARTIAL" if partial else "COMPLETED",
        "agents": progress, "coverage": coverage, "evidence_count": len(state.normalized_evidence) if state.iteration else min(20, len(refs)),
        "uncertainty": "관측 근거이며 원인 확정은 아닙니다.",
        "updated_at": max((p["updated_at"] for p in progress), default=run.started_at.isoformat())}


def projection(run, branches=None):
    state = run.state
    return {**run.model_dump(mode="json", exclude={"tenant_id", "state", "requested_by",
            "delegated_roles", "delegated_store_scope", "initial_incident_version", "manifest"}),
        "route": state.route, "risk_level": state.risk_level,
        "tools": [{"name": c.tool_name, "version": c.tool_version,
            "status": "COMPLETED" if c.result else "FAILED" if c.error else "PENDING",
            "message": c.error.safe_message if c.error else
                ({"get_incident": "사건 자료 확인 완료", "search_similar_incidents": "유사 사례 확인 완료",
                  "get_transactions": "거래 자료 확인 완료", "get_inventory": "재고 자료 확인 완료"}[c.tool_name]
                 if c.result and c.result.items else "필요한 자료가 없습니다." if c.result else "자료를 확인하고 있습니다."),
            "evidence_count": len(c.result.items) if c.result else 0,
            "error_code": c.error.code if c.error else None,
            "human_action": c.error.human_action if c.error else "NONE"} for c in state.tool_calls],
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


def runtime_projection(uow, run, principal, store):
    if run.state.loop is None:
        return None
    events = uow.agent_runs.events(run.agent_run_id)
    control = control_state(events)
    reason = control if control != "RUNNING" else run.state.loop.termination
    messages = {"COMPLETED": "설정된 범위의 자동 조사를 완료했습니다.",
        "NO_NEW_EVIDENCE": "추가 자동 조사에서 새로운 근거를 찾지 못해 조사를 중단했습니다.",
        "BUDGET_EXHAUSTED": "설정된 자동 조사 한도에 도달했습니다. 담당자가 추가 조사 범위를 검토해 주세요.",
        "ITERATION_LIMIT": "자동 조사 반복 한도에 도달했습니다.", "POLICY_DENIED": "현재 안전 정책에 따라 자동 조사를 중단했습니다.",
        "PAUSED": "자동 조사를 일시정지했습니다. 확보한 근거는 유지합니다.", "STOPPED": "자동 조사를 중단했습니다. 자동으로 재개하지 않습니다.",
        "MANUAL_TAKEOVER": "담당자가 직접 처리를 이어가고 있습니다.", "INCOMPLETE": "실행 결과가 불확실해 담당자의 확인이 필요합니다."}
    eligible = allowed(principal, "operate", store) and run.status not in {"COMPLETED", "FAILED"}
    policy = run.state.loop.policy
    version = uow.configs.current()
    operations = min(policy.max_operations, version.config.max_tool_calls) if version else 0
    resumable = bool(version and version.config.loop_enabled and version.config.auto_investigation)
    return {"control_status": control, "control_version": sum(e.kind == "CONTROL" for e in events),
        "termination_reason": reason, "message": messages.get(reason, "사용 가능한 자료를 제한된 범위에서 조사하고 있습니다."),
        "budget_summary": f"읽기 조사 {run.state.tool_call_count} / {operations}회 · 반복 {run.state.iteration} / {policy.max_iterations}회",
        "remaining_operations": max(0, operations-run.state.tool_call_count), "new_evidence": run.state.loop.new_evidence,
        "human_action": "담당자가 근거와 조사 범위를 검토해 주세요." if reason in {"BUDGET_EXHAUSTED", "NO_NEW_EVIDENCE", "INCOMPLETE", "POLICY_DENIED", "MANUAL_TAKEOVER"} else "확보한 근거와 승인 요청을 확인해 주세요.",
        "permissions": {"pause": eligible and control == "RUNNING", "resume": eligible and control == "PAUSED" and resumable,
            "stop": eligible and control in {"RUNNING", "PAUSED"}, "takeover": eligible and control in {"RUNNING", "PAUSED"}},
        "versions": {"workflow": run.workflow_version, "config": str(run.config_version),
            "loop": policy.version, "harness": run.manifest.harness_policy_version if run.manifest else "legacy",
            **({"tool_bundle": ", ".join(run.manifest.tool_bundle_versions),
                "prompts": ", ".join(p.prompt_id+":"+p.version for p in run.manifest.prompt_versions)}
               if run.manifest and run.manifest.tool_bundle_versions else {})}}


def projected_run(uow, run, principal=None, store=None):
    stored = {b.agent_type: b for b in run.state.branches}
    for a in (run.state.selection.selected if run.state.selection else ()):
        result = uow.agent_runs.branch(run.agent_run_id, a.agent_type)
        if result is not None:
            stored[a.agent_type] = result
    branches = tuple(stored[k] for k in sorted(stored))
    return projection(run) | {"investigation": investigation_projection(run, branches),
        "runtime": runtime_projection(uow, run, principal, store) if principal else None}


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
                    detail = projected_run(uow, run, self.principal, incident.store)
                    if run.state.approval:
                        approval = uow.approvals.get(run.state.approval.approval_id)
                        if approval and approval.agent_run_id == run.agent_run_id:
                            detail["approval"].update(status=approval.status, decision_actor=approval.decided_by,
                                decision_reason_code="HUMAN_APPROVED" if approval.status == "APPROVED"
                                else "HUMAN_REJECTED" if approval.status == "REJECTED" else None)
                    return {**detail, "steps": [s.model_dump(mode="json", exclude={"result"})
                            for s in uow.agent_runs.steps(run_id)]}
                runs = uow.agent_runs.history(incident_id, limit+1, offset)
                return {"runs": [projected_run(uow, r, self.principal, incident.store) for r in runs[:limit]], "limit": limit,
                        "offset": offset, "has_more": len(runs)>limit}
        except psycopg.Error as error:
            raise AgentRunsUnavailable() from error


class IncidentAXQueries:
    """Tenant-scoped read projection; commands and technical checkpoints stay separate."""

    def __init__(self, persistence, context):
        self.persistence, self.context = persistence, context

    def get(self, incident_id):
        principal = self.context.principal
        require(principal, "read")
        try:
            with self.persistence.transaction(principal.tenant_id) as uow:
                incident = uow.incidents.get(incident_id)
                if incident is None:
                    raise IncidentNotFound()
                require(principal, "read", incident.store)
                runs = uow.agent_runs.history(incident_id, 1, 0)
                run = runs[0] if runs else None
                investigation = projected_run(uow, run)["investigation"] if run else None
                view = project_incident(incident, run, investigation)
                decisions = uow.decisions.history(incident_id, 1, 0)
                updates = {}
                review = False
                if view.decision_reference is None and decisions:
                    updates["decision_reference"] = decisions[0].decision_id
                if run and run.state.approval:
                    approval = uow.approvals.get(run.state.approval.approval_id)
                    if approval and approval.incident_id == incident_id and approval.agent_run_id == run.agent_run_id:
                        updates["approval_status"] = approval.status
                        review = ReviewQueries(IncidentService(uow.incidents, principal=principal),
                            uow.approvals, self.context, uow.configs.current()).get(approval.approval_id)["approval"]["actions"]["approve"]["allowed"]
                runtime = runtime_projection(uow, run, principal, incident.store) if run else None
                updates["runtime"] = AgentControlView.model_validate(runtime) if runtime else None
                uncertain = bool(run and any(c.error and c.error.code == "OUTCOME_UNKNOWN" or
                    not c.error and not c.result for c in run.state.tool_calls))
                view = explain(view.model_copy(update=updates), run)
                return next_action(view, operate=allowed(principal, "operate", incident.store),
                    review=review, control=runtime["control_status"] if runtime else "RUNNING",
                    termination=runtime["termination_reason"] if runtime else None, uncertain_effect=uncertain)
        except psycopg.Error as error:
            raise AgentRunsUnavailable() from error
