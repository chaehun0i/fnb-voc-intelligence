"""시간·저장소·외부 서비스 없이 안전 gate와 위험도를 판정합니다."""
from dataclasses import dataclass
from datetime import datetime

from src.decision.jev.models import (
    AgentType,
    Category,
    DecisionContext,
    DecisionValidationError,
    RequestedMode,
)
from src.decision.jev.models import (
    DecisionReasonCode as Reason,
)
from src.domain.config.models import ResolvedConfig
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import IncidentStatus, Priority, Severity

RISK_ORDER = tuple(Severity)
INVESTIGABLE = frozenset({IncidentStatus.DETECTED, IncidentStatus.TRIAGED,
                         IncidentStatus.INVESTIGATING, IncidentStatus.REOPENED})


@dataclass(frozen=True)
class SafetyResult:
    risk: Severity
    manual_gate: bool
    reasons: tuple[Reason, ...]


def validate(context: DecisionContext):
    if (not isinstance(context, DecisionContext) or not context.tenant_id or not context.incident_id
            or type(context.config_version) is not int or context.config_version < 0
            or not isinstance(context.occurred_at, datetime)
            or context.occurred_at.tzinfo is None or context.occurred_at.utcoffset() is None
            or type(context.recurrence_hint) is not bool
            or not isinstance(context.policy, ResolvedConfig)):
        raise DecisionValidationError("DECISION_VALIDATION_ERROR")
    for value, enum in ((context.incident_status, IncidentStatus), (context.severity, Severity),
                        (context.priority, Priority), (context.category, Category),
                        (context.requested_mode, RequestedMode)):
        if not isinstance(value, enum):
            raise DecisionValidationError("DECISION_VALIDATION_ERROR")
    if any(not isinstance(item, AgentType) for item in context.known_evidence_types + context.data_availability):
        raise DecisionValidationError("DECISION_VALIDATION_ERROR")
    ConfigResolver().resolve(context.policy.effective)


def safety_and_risk(context, *, critical_manual_only=True, blocked_categories=(Category.RESTRICTED,)):
    validate(context)
    reasons, gate = [], False
    risk = RISK_ORDER.index(context.severity)
    if context.category in {Category.FOOD_SAFETY, Category.COLD_CHAIN}:
        risk = max(risk, RISK_ORDER.index(Severity.HIGH))
        reasons.append(Reason.FOOD_SAFETY_RISK)
    if context.recurrence_hint:
        risk = min(risk+1, len(RISK_ORDER)-1)
        reasons.append(Reason.RECURRENCE_RISK)
    if not context.known_evidence_types:
        risk = max(risk, RISK_ORDER.index(Severity.MEDIUM))
        reasons.append(Reason.EVIDENCE_GAP)
    if critical_manual_only and RISK_ORDER[risk] == Severity.CRITICAL:
        gate = True
        reasons.append(Reason.CRITICAL_MANUAL_GATE)
    if context.category in blocked_categories:
        gate = True
        reasons.append(Reason.CATEGORY_BLOCKED)
    if not context.policy.effective.auto_investigation or context.requested_mode != RequestedMode.AUTO:
        gate = True
        reasons.append(Reason.MANUAL_REQUESTED if context.requested_mode == RequestedMode.MANUAL else Reason.AUTOMATION_DISABLED)
    if context.incident_status not in INVESTIGABLE:
        gate = True
        reasons.append(Reason.STATUS_NOT_INVESTIGABLE)
    return SafetyResult(RISK_ORDER[risk], gate, tuple(reasons))
