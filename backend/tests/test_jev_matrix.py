"""정규화된 사실과 정책만으로 판단하는 회귀 표입니다."""
import ast
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed
from src.domain.decisions.engine import JevEngine
from src.domain.decisions.models import AgentType as Agent
from src.domain.decisions.models import Category, DecisionValidationError, RequestedMode
from src.domain.incidents.enums import IncidentStatus, Severity

from .test_jev_contract import context

CASES = [
    ({}, {}, "GENERAL_INVESTIGATION"),
    ({"severity": Severity.CRITICAL}, {}, "MANUAL_REVIEW"),
    ({}, {"auto_investigation": False}, "MANUAL_REVIEW"),
    ({"category": Category.RESTRICTED}, {}, "MANUAL_REVIEW"),
    ({"category": Category.COLD_CHAIN}, {}, "COLD_CHAIN_INVESTIGATION"),
    ({"category": Category.SUPPLIER_LOT}, {}, "SUPPLIER_LOT_INVESTIGATION"),
    ({"recurrence_hint": True}, {}, "HISTORY_RECURRENCE"),
    ({"category": Category.TRANSACTION}, {}, "TRANSACTION_INVESTIGATION"),
    ({"category": Category.UNKNOWN}, {}, "GENERAL_INVESTIGATION"),
    ({}, {"allowed_agent_types": ()}, "MANUAL_REVIEW"),
    ({"data_availability": ()}, {}, "MANUAL_REVIEW"),
    ({}, {"parallelism": 1}, "GENERAL_INVESTIGATION"),
    ({}, {"hosted_ai_allowed": False}, "GENERAL_INVESTIGATION"),
    ({}, {"hosted_ai_allowed": True, "auto_rca_draft": True}, "GENERAL_INVESTIGATION"),
    ({"requested_mode": RequestedMode.MANUAL}, {}, "MANUAL_REVIEW"),
    ({"requested_mode": RequestedMode.ASSISTED}, {}, "MANUAL_REVIEW"),
    ({"incident_status": IncidentStatus.CLOSED}, {}, "MANUAL_REVIEW"),
    ({"incident_status": IncidentStatus.REOPENED}, {}, "GENERAL_INVESTIGATION"),
    ({"severity": Severity.HIGH, "recurrence_hint": True}, {}, "MANUAL_REVIEW"),
    ({"category": Category.COLD_CHAIN}, {"blocked_categories": ("RESTRICTED", "COLD_CHAIN")}, "MANUAL_REVIEW"),
    ({"category": Category.FOOD_SAFETY}, {}, "COLD_CHAIN_INVESTIGATION"),
    ({"known_evidence_types": ()}, {}, "GENERAL_INVESTIGATION"),
    ({"severity": Severity.CRITICAL}, {"critical_manual_only": False}, "GENERAL_INVESTIGATION"),
    ({}, {"allowed_agent_types": ("HISTORY",)}, "GENERAL_INVESTIGATION"),
]


@pytest.mark.parametrize("facts,policy,route", CASES)
def test_deterministic_decision_matrix(facts, policy, route):
    raw = RuntimeConfig(auto_investigation=True)
    raw = replace(raw, **policy)
    resolved = ConfigResolver().resolve(raw)
    value = context(known_evidence_types=tuple(Agent), data_availability=tuple(Agent),
                    policy=resolved, config_version=17)
    value = replace(value, **facts)
    before = value
    engine = JevEngine()
    result = engine.evaluate(value)
    assert result == engine.evaluate(value) and value == before
    assert result.route == route and result.mode == "SHADOW"
    assert result.config_version == 17 and result.ruleset_version == "1"
    assert len(result.investigation_agents) <= raw.parallelism
    assert all(agent in raw.allowed_agent_types and agent in value.data_availability for agent in result.investigation_agents)
    assert len(set(result.reason_codes)) == len(result.reason_codes)
    if route == "MANUAL_REVIEW":
        assert not result.investigation_agents and result.requires_human_review and not result.requires_llm
    if not raw.hosted_ai_allowed:
        assert not result.requires_llm and "PROVIDER_POLICY_DENIED" in result.reason_codes
    if value.recurrence_hint or value.category in {Category.COLD_CHAIN, Category.FOOD_SAFETY}:
        assert result.risk_level in {Severity.HIGH, Severity.CRITICAL} or value.severity == Severity.LOW


@pytest.mark.parametrize("change", [{"config_version": -1}, {"severity": "MEDIUM"}, {"occurred_at": datetime(2026, 1, 1, tzinfo=UTC).replace(tzinfo=None)}, {"occurred_at": "invalid"}, {"recurrence_hint": 1}])
def test_invalid_input_is_not_unknown_category(change):
    with pytest.raises(DecisionValidationError):
        JevEngine().evaluate(replace(context(), **change))
    with pytest.raises(DecisionValidationError):
        JevEngine().evaluate(None)


def test_pure_package_has_no_io_or_provider_dependency():
    root = Path(__file__).parents[1] / "src" / "decision" / "jev"
    forbidden = {"fastapi", "psycopg", "requests", "httpx", "random", "uuid", "time", "google", "ollama", "langgraph", "subprocess"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(alias.name.split(".")[0] in forbidden for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"now", "utcnow", "execute", "request", "save"}


@pytest.mark.parametrize("policy", [{"parallelism": 100}, {"allowed_agent_types": ("SHELL",)}, {"blocked_categories": ()}])
def test_current_config_safety_caps_cannot_be_bypassed(policy):
    with pytest.raises(ConfigValidationFailed):
        ConfigResolver().resolve(replace(RuntimeConfig(), **policy))
