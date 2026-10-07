"""Deterministic projection: no LLM, repository, command or provider effects."""
from datetime import datetime
from hashlib import sha256

from src.ai.ax.models import (
    AgentProgress,
    AIBrief,
    EvidenceCoverage,
    IncidentAX,
    NextBestAction,
)


def project_incident(incident, run=None, investigation=None):
    coverage = {k: [] for k in ("confirmed", "missing", "conflicting", "stale")}
    progress = []
    if investigation:
        for item in investigation["coverage"]:
            coverage[{"CONFIRMED": "confirmed", "MISSING": "missing", "CONFLICTING": "conflicting", "STALE": "stale"}[item["status"]]].append(item["dimension"])
        progress = [AgentProgress(agent_type=a["agent_type"], label=a["business_label"],
            status=a["status"], evidence_count=a["evidence_count"]) for a in investigation["agents"]]
    state = run.state if run else None
    count = len(state.normalized_evidence) if state else min(20, sum(e.status == "AVAILABLE" for e in incident.evidence))
    if state and not investigation and state.sufficiency:
        # Legacy single-History runs have no AgentSelection; do not lose their insufficiency.
        if count:
            coverage["confirmed"].append("HISTORY")
        if state.sufficiency.status == "INSUFFICIENT":
            coverage["missing"].append("HISTORY")
        elif state.sufficiency.status == "CONFLICTING":
            coverage["conflicting"].append("HISTORY")
    result = state.verification.result if state and state.verification else (
        incident.verification.result.value if incident.verification else None)
    hypothesis = "반복 이력에 공통 신호가 있어 추가 원인 검토가 필요합니다." if state and state.rca_candidates else None
    timestamps = [incident.created_at, *(t.occurred_at for t in incident.timeline)]
    if run:
        timestamps.append((run.completed_at or run.started_at).isoformat())
    return IncidentAX(incident_id=incident.id, current_phase=incident.status.value,
        brief=AIBrief(headline="사건의 조사와 처리 상태를 확인해 주세요.",
            summary=f"확인된 조사 근거는 {count}개입니다. 근거와 검증 결과를 구분해 확인해 주세요.",
            primary_hypothesis=hypothesis, confidence_level="MEDIUM" if hypothesis else "INCONCLUSIVE"),
        coverage=EvidenceCoverage(**coverage, evidence_count=count), progress=tuple(progress),
        next_action=NextBestAction(risk=incident.severity.value),
        uncertainties=("관측 근거이며 물리적 원인이 확정된 것은 아닙니다.",) if state else ("아직 자동 조사 결과가 없습니다.",),
        source_run_id=run.agent_run_id if run else None,
        manifest_reference=sha256(run.manifest.model_dump_json().encode()).hexdigest() if run and run.manifest else None,
        decision_reference=run.jev_decision_id if run else None,
        verification_result=result, execution_mode=state.execution.execution_mode if state and state.execution else None,
        approval_status=state.approval.status if state and state.approval else None,
        updated_at=max(datetime.fromisoformat(t) for t in timestamps))
