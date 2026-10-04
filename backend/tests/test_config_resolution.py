"""보안 판단은 UI가 아니라 서버의 결정적 설정 해석에 있습니다."""
from dataclasses import replace

import pytest

from src.domain.config.models import RiskApproval, RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed


def test_resolution_is_deterministic_and_future_runtime_is_not_connected():
    resolver = ConfigResolver()
    config = RuntimeConfig(auto_execute=True)
    assert resolver.resolve(config) == resolver.resolve(config)
    assert resolver.resolve(config).effective.approval_policy_by_risk.HIGH
    assert resolver.resolve(config).runtime_status == "NOT_CONNECTED"
    assert dict(resolver.resolve(config).sources)["max_tool_calls"] == "TENANT"


@pytest.mark.parametrize("changes", [
    {"max_tool_calls": 100}, {"parallelism": 11}, {"tenant_queue_concurrency": 0},
    {"max_agent_iterations": True}, {"cost_budget_usd": float("nan")},
    {"jev_enabled": "yes"}, {"allowed_tools": ("execute_sql",)},
    {"auto_execute": True, "approval_policy_by_risk": RiskApproval(HIGH=False)},
    {"separation_of_duties": False}, {"required_roles": ("AUDITOR",)},
    {"critical_approver_count": 1}, {"default_llm_provider": "unknown"},
])
def test_safety_caps_and_approval_cannot_be_bypassed(changes):
    with pytest.raises(ConfigValidationFailed) as error:
        ConfigResolver().resolve(replace(RuntimeConfig(), **changes))
    assert error.value.details[0]["field"]


def test_new_caps_revalidate_historical_snapshots():
    resolver = ConfigResolver(rules={"max_tool_calls": (1, 10, True)})
    with pytest.raises(ConfigValidationFailed):
        resolver.resolve(RuntimeConfig(max_tool_calls=20))
