"""Outcome summaries and provenance, never private model reasoning."""
from src.ai.ax.models import AIBrief, Explanation

PHASE_LABELS = {
    "DETECTED": "문제 접수", "TRIAGED": "조사 준비", "INVESTIGATING": "근거 조사",
    "RCA_READY": "원인 후보 검토", "ACTION_PROPOSED": "조치안 검토", "PENDING_APPROVAL": "사람의 승인 대기",
    "EXECUTING": "내부 실행 기록", "VERIFYING": "검증 근거 확인", "RESOLVED": "검증 통과 · 해결",
    "REOPENED": "검증 실패 · 재조사 필요", "CLOSED": "사건 종결", "BLOCKED": "진행 차단",
    "ESCALATED": "담당자 검토 필요", "FAILED": "업무 처리 실패",
}


def explain(view, run=None):
    state = run.state if run else None
    sufficiency = state.sufficiency if state else None
    statements = [f"확인된 조사 근거는 {view.coverage.evidence_count}개입니다."]
    if view.approval_status == "APPROVED" and view.execution_mode is None:
        statements.append("조치안은 승인되었지만 실행 완료는 아닙니다.")
    elif view.execution_mode:
        statements.append("승인된 조치의 내부 실행 기록이며 외부 시스템은 변경하지 않았습니다.")
    if view.verification_result:
        statements.append({"PASS": "내부 검증 기준을 충족했습니다.", "FAIL": "검증 기준을 충족하지 못해 재조사가 필요합니다.",
            "INCONCLUSIVE": "검증 근거가 부족해 검증 상태를 유지합니다."}[view.verification_result])
    else:
        statements.append("현장 개선 효과는 아직 검증되지 않았습니다.")
    if sufficiency and sufficiency.status != "SUFFICIENT":
        statements.append("부족하거나 상충하는 근거가 있어 원인을 확정하지 않았습니다.")
    gaps = tuple(sorted({g.code for g in state.evidence_gaps})) if state else ()
    if sufficiency:
        gaps = tuple(sorted(set(gaps) | {g.code for g in sufficiency.evidence_gaps}))
    return view.model_copy(update={
        "brief": AIBrief(headline=PHASE_LABELS[view.current_phase], summary=" ".join(statements),
            primary_hypothesis=state.rca_candidates[0].hypothesis if state and state.rca_candidates else None,
            confidence_level="MEDIUM" if sufficiency and sufficiency.status == "SUFFICIENT" else "INCONCLUSIVE"),
        "explanation": Explanation(supporting_refs=sufficiency.supporting_refs if sufficiency else (),
            contradicting_refs=sufficiency.contradicting_refs if sufficiency else (), missing_codes=gaps,
            assumptions=("거래·재고 관측은 입력된 자료이며 실제 POS/ERP 연결이 아닙니다.",),
            cannot_verify=("물리적 근본 원인과 실제 현장 개선 효과를 확정하지 않습니다.",),
            technical_trace_available=run is not None)})
