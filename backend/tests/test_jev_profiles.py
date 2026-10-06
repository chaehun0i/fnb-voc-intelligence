from src.domain.decisions.models import AgentType, Category, DecisionRoute
from src.domain.decisions.profiles import select_profile
from src.domain.decisions.rules import safety_and_risk
from tests.test_jev_safety import active


def test_profile_is_ordered_bounded_and_drops_unavailable_data():
    value = active(category=Category.COLD_CHAIN, data_availability=tuple(AgentType))
    route, agents, _ = select_profile(value, safety_and_risk(value), tuple(AgentType), 2)
    assert route == DecisionRoute.COLD_CHAIN_INVESTIGATION
    assert agents == (AgentType.TEMPERATURE, AgentType.INVENTORY)
    assert select_profile(value, safety_and_risk(value), (), 2)[0] == DecisionRoute.MANUAL_REVIEW
    empty = active()
    assert select_profile(empty, safety_and_risk(empty), tuple(AgentType), 2)[1] == ()
