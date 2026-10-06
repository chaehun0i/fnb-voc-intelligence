"""정렬된 후보 목록은 향후 조사 제안이며 Agent를 실행하지 않습니다."""
from src.routing.models import (
    AgentType,
    Category,
    DecisionReasonCode,
    DecisionRoute,
)

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
