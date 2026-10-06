"""ai/decision/engine: 통합된 기능 책임, 기존 실행 계약 유지."""
from dataclasses import dataclass
from datetime import datetime

from src.ai.decision.models import (
    AgentType,
    Category,
    DecisionContext,
    DecisionReasonCode,
    DecisionResult,
    DecisionRoute,
    DecisionValidationError,
    RequestedMode,
)
from src.ai.decision.models import (
    DecisionReasonCode as Reason,
)
from src.domain.config.models import ResolvedConfig
from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.enums import (
    EvidenceStatus,
    IncidentStatus,
    Priority,
    Severity,
)

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


PROFILES = {
    DecisionRoute.COLD_CHAIN_INVESTIGATION: (AgentType.TEMPERATURE, AgentType.INVENTORY, AgentType.HISTORY),
    DecisionRoute.SUPPLIER_LOT_INVESTIGATION: (AgentType.LOT, AgentType.SUPPLIER, AgentType.INVENTORY, AgentType.HISTORY),
    DecisionRoute.HISTORY_RECURRENCE: (AgentType.HISTORY, AgentType.TRANSACTION),
    DecisionRoute.TRANSACTION_INVESTIGATION: (AgentType.TRANSACTION, AgentType.HISTORY),
    DecisionRoute.GENERAL_INVESTIGATION: (AgentType.HISTORY, AgentType.TRANSACTION, AgentType.INVENTORY),
    DecisionRoute.MANUAL_REVIEW: (),
}


def select_profile(context, safety, allowed_agents, max_parallelism):
    reasons = []
    if safety.manual_gate:
        return DecisionRoute.MANUAL_REVIEW, (), ()
    if context.category in {Category.COLD_CHAIN, Category.FOOD_SAFETY}:
        route = DecisionRoute.COLD_CHAIN_INVESTIGATION
    elif context.category == Category.SUPPLIER_LOT:
        route = DecisionRoute.SUPPLIER_LOT_INVESTIGATION
    elif context.recurrence_hint:
        route = DecisionRoute.HISTORY_RECURRENCE
    elif context.category == Category.TRANSACTION:
        route = DecisionRoute.TRANSACTION_INVESTIGATION
    else:
        route = DecisionRoute.GENERAL_INVESTIGATION
        if context.category == Category.UNKNOWN:
            reasons.append(DecisionReasonCode.UNKNOWN_CATEGORY)
    allowed = tuple(agent for agent in PROFILES[route] if agent in allowed_agents)
    available = tuple(agent for agent in allowed if agent in context.data_availability)
    if len(available) != len(allowed):
        reasons.append(DecisionReasonCode.DATA_UNAVAILABLE)
    if not allowed:
        reasons.append(DecisionReasonCode.NO_ALLOWED_AGENTS)
    if not available:
        if DecisionReasonCode.DATA_UNAVAILABLE not in reasons and allowed:
            reasons.append(DecisionReasonCode.DATA_UNAVAILABLE)
        return DecisionRoute.MANUAL_REVIEW, (), tuple(reasons)
    if len(available) > max_parallelism:
        reasons.append(DecisionReasonCode.PARALLELISM_LIMIT)
    return route, available[:max_parallelism], tuple(reasons)


def build_context(incident, resolved, config_version, *, requested_mode=RequestedMode.AUTO):
    # category/recurrence가 Incident에 없으므로 제목·VOC에서 추측하지 않습니다.
    present = tuple(agent for agent in AgentType if any(e.type.upper() == agent.value for e in incident.evidence))
    available = tuple(agent for agent in present if any(e.type.upper() == agent.value and e.status == EvidenceStatus.AVAILABLE for e in incident.evidence))
    category = Category.COLD_CHAIN if AgentType.TEMPERATURE in present else (
        Category.SUPPLIER_LOT if AgentType.LOT in present or AgentType.SUPPLIER in present else
        Category.TRANSACTION if AgentType.TRANSACTION in present else Category.UNKNOWN)
    return DecisionContext(incident.tenant_id, incident.id, incident.status, incident.severity,
        incident.priority, category, incident.store, present, available, False, requested_mode,
        resolved, config_version, datetime.fromisoformat(incident.created_at))


class JevEngine:
    def evaluate(self, context):
        validate(context)
        config = context.policy.effective
        safety = safety_and_risk(context, critical_manual_only=config.critical_manual_only,
                                 blocked_categories=config.blocked_categories)
        route, agents, profile_reasons = select_profile(context, safety,
            tuple(AgentType(a) for a in config.allowed_agent_types), config.parallelism)
        reasons = [*safety.reasons, *profile_reasons]
        if not config.hosted_ai_allowed:
            reasons.append(DecisionReasonCode.PROVIDER_POLICY_DENIED)
        manual = route == DecisionRoute.MANUAL_REVIEW
        human = manual or getattr(config.approval_policy_by_risk, str(safety.risk))
        if human:
            reasons.append(DecisionReasonCode.HUMAN_REVIEW_REQUIRED)
        priority = Priority.P1 if safety.risk in {Severity.HIGH, Severity.CRITICAL} else context.priority
        return DecisionResult(route, safety.risk, priority, agents,
            bool(agents) and config.hosted_ai_allowed and (config.auto_rca_draft or config.auto_capa_draft),
            human, "manual-review-v1" if manual else "incident-investigation-v1",
            "high" if priority == Priority.P1 else "small" if safety.risk == Severity.LOW else "standard",
            " / ".join(str(r) for r in reasons) if manual or not config.hosted_ai_allowed else None,
            tuple(dict.fromkeys(reasons)), context.config_version)
