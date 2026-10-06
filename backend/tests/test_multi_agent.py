from datetime import UTC, datetime, timedelta

import pytest

from src.ai.workflow.models import TenantCapability
from src.ai.workflow.policy import select_agents

NOW = datetime(2026, 10, 6, tzinfo=UTC)


def capability(kind="HISTORY_DATA", **updates):
    return TenantCapability(tenant_id="tenant-a", store="store-a", capability=kind,
        available=True, source="AUTHORIZED_HISTORY_SEARCH", health="HEALTHY",
        freshness="FRESH", checked_at=NOW).model_copy(update=updates)


def selection(capabilities, **updates):
    args = {"tenant_id": "tenant-a", "store": "store-a", "category": "GENERAL",
        "allowed_agents": ("HISTORY", "TRANSACTION", "INVENTORY"), "now": NOW}
    return select_agents(("HISTORY", "TRANSACTION", "INVENTORY", "TEMPERATURE"), capabilities, **(args | updates))


def test_registry_intersection_is_deterministic():
    result = selection([capability()])
    assert tuple(a.agent_type for a in result.selected) == ("HISTORY",)
    assert result.excluded == ("TRANSACTION", "INVENTORY")


@pytest.mark.parametrize("updates", [{"available": False}, {"freshness": "STALE"},
    {"checked_at": NOW-timedelta(minutes=6)}, {"checked_at": NOW+timedelta(seconds=1)}])
def test_unavailable_or_stale_capability_not_executed(updates):
    assert not selection([capability(**updates)]).selected


def test_capability_tenant_and_store_fail_closed():
    for updates in ({"tenant_id": "other"}, {"store": "other"}):
        with pytest.raises(ValueError, match="SCOPE_MISMATCH"):
            selection([capability(**updates)])


def test_disabled_or_category_filtered():
    assert not selection([capability()], allowed_agents=()).selected
    assert not selection([capability()], category="RESTRICTED").selected
