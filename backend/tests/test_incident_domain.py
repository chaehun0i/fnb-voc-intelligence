from dataclasses import replace

import pytest

from src.domain.incidents.enums import IncidentStatus, Severity, VerificationResult
from src.domain.incidents.models import Incident, Verification
from src.domain.incidents.transitions import DomainRuleViolation, transition


def incident():
    return Incident(
        "1",
        "INC-1",
        "test",
        Severity.HIGH,
        IncidentStatus.DETECTED,
        "store",
        "owner",
        "2026-01-01",
        "2026-01-02",
    )


def test_transition():
    assert (
        transition(incident(), IncidentStatus.TRIAGED, "2026-01-01").status
        == IncidentStatus.TRIAGED
    )


def test_skip_rejected():
    with pytest.raises(DomainRuleViolation):
        transition(incident(), IncidentStatus.EXECUTING, "2026-01-01")


def test_transition_returns_new_model_without_mutating_original():
    original = incident()
    result = transition(original, IncidentStatus.TRIAGED, "2026-01-01")
    assert original.status == IncidentStatus.DETECTED
    assert original.timeline == []
    assert result.timeline[0].status == IncidentStatus.TRIAGED


def test_execution_requires_approval():
    pending = replace(incident(), status=IncidentStatus.PENDING_APPROVAL)
    with pytest.raises(DomainRuleViolation):
        transition(pending, IncidentStatus.EXECUTING, "2026-01-01")
    approved = replace(pending, approved=True)
    assert (
        transition(approved, IncidentStatus.EXECUTING, "2026-01-01").status
        == IncidentStatus.EXECUTING
    )


@pytest.mark.parametrize(
    "result", [None, VerificationResult.FAIL, VerificationResult.INCONCLUSIVE]
)
def test_resolution_requires_verification_pass(result):
    verification = Verification(result, "확인 결과") if result else None
    checking = replace(
        incident(), status=IncidentStatus.VERIFYING, verification=verification
    )
    with pytest.raises(DomainRuleViolation):
        transition(checking, IncidentStatus.RESOLVED, "2026-01-01")


def test_failed_verification_reopens_only_verifying_stage():
    failed = replace(
        incident(),
        status=IncidentStatus.VERIFYING,
        approved=True,
        verification=Verification(VerificationResult.FAIL, "이상이 반복되었습니다."),
    )
    reopened = transition(failed, IncidentStatus.REOPENED, "2026-01-01")
    assert reopened.status == IncidentStatus.REOPENED
    assert reopened.approved is False
    with pytest.raises(DomainRuleViolation):
        transition(
            replace(failed, status=IncidentStatus.DETECTED),
            IncidentStatus.REOPENED,
            "2026-01-01",
        )


def test_closed_incident_cannot_resume_even_with_recurrence():
    closed = replace(incident(), status=IncidentStatus.CLOSED)
    with pytest.raises(DomainRuleViolation):
        transition(closed, IncidentStatus.REOPENED, "2026-01-01", recurrence=True)


def test_resolved_recurrence_needs_explicit_condition():
    resolved = replace(incident(), status=IncidentStatus.RESOLVED)
    with pytest.raises(DomainRuleViolation):
        transition(resolved, IncidentStatus.REOPENED, "2026-01-01")
    assert (
        transition(
            resolved, IncidentStatus.REOPENED, "2026-01-01", recurrence=True
        ).status
        == IncidentStatus.REOPENED
    )


def test_domain_rejects_invalid_verification_and_confidence():
    from src.domain.incidents.models import Evidence

    with pytest.raises(ValueError):
        Verification("INVALID", "잘못된 판정")
    with pytest.raises(ValueError):
        Evidence("e1", "센서", "TEMP", "관측", float("nan"))
    with pytest.raises(ValueError):
        replace(incident(), version=-1)
