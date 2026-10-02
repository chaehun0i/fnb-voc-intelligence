"""인시던트 상태 변경을 한 곳에서 결정합니다."""

from dataclasses import replace

from .enums import IncidentStatus, VerificationResult
from .models import Incident, StateTransition


class DomainRuleViolation(ValueError):
    """요청한 업무 동작이 현재 상태 또는 증거와 맞지 않습니다."""


_NEXT = {
    IncidentStatus.DETECTED: IncidentStatus.TRIAGED,
    IncidentStatus.TRIAGED: IncidentStatus.INVESTIGATING,
    IncidentStatus.INVESTIGATING: IncidentStatus.RCA_READY,
    IncidentStatus.RCA_READY: IncidentStatus.ACTION_PROPOSED,
    IncidentStatus.ACTION_PROPOSED: IncidentStatus.PENDING_APPROVAL,
    IncidentStatus.PENDING_APPROVAL: IncidentStatus.EXECUTING,
    IncidentStatus.EXECUTING: IncidentStatus.VERIFYING,
    IncidentStatus.VERIFYING: IncidentStatus.RESOLVED,
    IncidentStatus.RESOLVED: IncidentStatus.CLOSED,
    IncidentStatus.REOPENED: IncidentStatus.INVESTIGATING,
}


def require_status(incident: Incident, *statuses: IncidentStatus) -> None:
    if incident.status not in statuses:
        raise DomainRuleViolation("현재 단계에서는 요청한 동작을 진행할 수 없습니다.")


def transition(
    incident: Incident,
    target: IncidentStatus,
    occurred_at: str,
    *,
    recurrence: bool = False,
    rejected: bool = False,
    reason: str | None = None,
) -> Incident:
    """검증 후 새 모델을 반환해 실패한 명령이 원본을 바꾸지 않게 합니다."""
    if incident.status is IncidentStatus.CLOSED:
        raise DomainRuleViolation("종료한 인시던트는 새 인시던트로 접수해야 합니다.")
    if (
        rejected
        and incident.status is IncidentStatus.PENDING_APPROVAL
        and target is IncidentStatus.ACTION_PROPOSED
    ):
        return replace(
            incident,
            status=target,
            approved=False,
            timeline=[*incident.timeline, StateTransition(target, occurred_at, reason)],
        )
    if target is IncidentStatus.REOPENED:
        failed_verification = (
            incident.status is IncidentStatus.VERIFYING
            and incident.verification is not None
            and incident.verification.result == VerificationResult.FAIL
        )
        recurring = recurrence and incident.status is IncidentStatus.RESOLVED
        if not (failed_verification or recurring):
            raise DomainRuleViolation(
                "검증 실패 또는 해결 이후 재발 근거가 필요합니다."
            )
        return replace(
            incident,
            status=target,
            approved=False,
            root_cause_candidates=[],
            corrective_actions=[],
            timeline=[*incident.timeline, StateTransition(target, occurred_at, reason)],
        )
    if _NEXT.get(incident.status) != target:
        raise DomainRuleViolation("허용되지 않은 상태 전이입니다.")
    if target is IncidentStatus.RCA_READY and not incident.root_cause_candidates:
        raise DomainRuleViolation("원인 후보가 필요합니다.")
    if target is IncidentStatus.ACTION_PROPOSED and not incident.corrective_actions:
        raise DomainRuleViolation("시정·예방 조치안이 필요합니다.")
    if target is IncidentStatus.EXECUTING and not incident.approved:
        raise DomainRuleViolation("실행 전에 사람의 승인이 필요합니다.")
    if target is IncidentStatus.RESOLVED and (
        incident.verification is None
        or incident.verification.result != VerificationResult.PASS
    ):
        raise DomainRuleViolation("검증 결과가 통과여야 해결할 수 있습니다.")
    return replace(
        incident,
        status=target,
        timeline=[*incident.timeline, StateTransition(target, occurred_at, reason)],
    )
