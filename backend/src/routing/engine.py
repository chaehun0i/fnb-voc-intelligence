"""같은 입력에서 같은 의미의 결과를 반환하는 순수 판단 엔진입니다."""
from src.domain.incidents.enums import Priority, Severity
from src.routing.models import (
    AgentType,
    DecisionReasonCode,
    DecisionResult,
    DecisionRoute,
)
from src.routing.profiles import select_profile
from src.routing.rules import safety_and_risk, validate


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
