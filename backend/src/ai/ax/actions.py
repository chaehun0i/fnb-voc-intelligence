"""User task selection only; existing authorization/review commands remain authoritative."""
from src.ai.ax.models import NextBestAction


def next_action(view, *, operate=False, review=False, control="RUNNING", termination=None,
                uncertain_effect=False):
    human, action, label, reason, permission, approval = (
        "NONE", "CHECK_RESULT", "처리 결과 확인", "현재 사건과 조사 결과를 확인해 주세요.", True, False)
    if uncertain_effect or termination == "INCOMPLETE":
        human, action, label, reason = ("MANUAL_TAKEOVER_RECOMMENDED", "MANUAL_REVIEW",
            "이전 요청 결과 확인", "결과가 불확실합니다. 다시 실행하지 말고 기존 기록을 확인해 주세요.")
        permission = operate
    elif control in {"STOPPED", "MANUAL_TAKEOVER"}:
        human, action, label, reason = ("REVIEW_REQUIRED", "MANUAL_REVIEW", "담당자 직접 검토",
            "자동 작업은 중단되어 있습니다. 확보한 근거를 유지하며 직접 처리해 주세요.")
        permission = operate
    elif termination == "POLICY_DENIED":
        human, action, label, reason = ("POLICY_BLOCKED", "MANUAL_REVIEW", "안전 정책 확인",
            "현재 정책에서 자동 진행을 허용하지 않습니다.")
        permission = operate
    elif view.approval_status == "PENDING":
        human, action, label, reason = ("APPROVAL_REQUIRED", "OPEN_REVIEW", "조치안 승인 검토",
            "조치안은 아직 승인되지 않았습니다. 기존 검토 화면에서 결정해 주세요.")
        permission, approval = review, True
    elif view.approval_status == "REJECTED":
        human, action, label, reason = ("REVIEW_REQUIRED", "MANUAL_REVIEW", "반려된 조치안 검토",
            "조치안이 반려되었습니다. 실행하지 않고 근거와 조치안을 검토해 주세요.")
        permission = operate
    elif view.current_phase in {"RESOLVED", "CLOSED"}:
        reason = "검증과 사건 처리 결과를 확인해 주세요. 해결과 종결은 서로 다른 상태입니다."
    elif view.current_phase == "VERIFYING":
        human, action, label, reason = ("VERIFICATION_REQUIRED", "VERIFY", "검증 근거 확인",
            "검증 근거와 기준을 확인해 주세요. 판정 불가는 해결 완료가 아닙니다.")
        permission = operate
    elif view.approval_status == "APPROVED" and view.execution_mode is None:
        human, action, label, reason = ("REVIEW_REQUIRED", "CHECK_RESULT", "승인 후 진행 확인",
            "승인 완료 — 실행 단계 대기입니다. 승인만으로 실행 완료를 의미하지 않습니다.")
    elif termination in {"BUDGET_EXHAUSTED", "ITERATION_LIMIT"}:
        human, action, label, reason = ("BUDGET_INCREASE_REQUIRED", "MANUAL_REVIEW", "조사 범위 검토",
            "자동 조사 한도에 도달했습니다. 한도를 자동 상향하지 않고 담당자 검토를 기다립니다.")
        permission = operate
    elif view.coverage.missing or view.coverage.conflicting or termination == "NO_NEW_EVIDENCE":
        human, action, label, reason = ("MORE_EVIDENCE_REQUIRED", "COLLECT_EVIDENCE", "추가 근거 확인",
            "부족하거나 상충하는 근거가 있습니다. 원인을 확정하지 말고 근거를 확인해 주세요.")
        permission = operate
    elif view.current_phase in {"RCA_READY", "ACTION_PROPOSED", "REOPENED"}:
        human, action, label, reason = ("REVIEW_REQUIRED", "OPEN_WORKSPACE", "근거와 조치안 검토",
            "담당자가 근거와 조치안을 확인해 주세요.")
        permission = operate
    return view.model_copy(update={"human_action": human, "next_action": NextBestAction(
        action_type=action, label=label, reason=reason, risk=view.next_action.risk,
        permission=permission, requires_approval=approval,
        blocking_reason=None if permission else "현재 권한 또는 승인 정책에서 이 작업을 허용하지 않습니다.",
        alternative_actions=("CHECK_RESULT",) if action != "CHECK_RESULT" else ())})
