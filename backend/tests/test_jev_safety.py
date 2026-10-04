from dataclasses import replace

import pytest

from src.decision.jev.models import (
    Category,
    DecisionReasonCode,
    DecisionValidationError,
)
from src.decision.jev.rules import safety_and_risk
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import Severity
from tests.test_jev_contract import context


def active(**changes):
    current = context(**changes)
    return replace(current, policy=ConfigResolver().resolve(replace(current.policy.effective, auto_investigation=True)))


def test_hard_rules_cannot_be_weakened_by_risk_escalation():
    result = safety_and_risk(active(severity=Severity.HIGH, recurrence_hint=True))
    assert result.risk == Severity.CRITICAL and result.manual_gate
    assert DecisionReasonCode.CRITICAL_MANUAL_GATE in result.reasons
    assert safety_and_risk(active(category=Category.RESTRICTED)).manual_gate
    assert safety_and_risk(context()).manual_gate


def test_unknown_category_is_valid_but_invalid_type_is_rejected():
    assert not safety_and_risk(active(category=Category.UNKNOWN)).manual_gate
    with pytest.raises(DecisionValidationError):
        safety_and_risk(active(category="raw customer text"))
