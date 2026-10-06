from dataclasses import replace

from src.domain.config.resolution import ConfigResolver
from src.domain.incidents.models import Incident
from src.routing.context import build_context
from src.routing.engine import JevEngine
from src.routing.models import AgentType, Category
from tests.test_jev_safety import active


def test_engine_is_deterministic_and_propagates_config():
    value = active(category=Category.TRANSACTION, data_availability=(AgentType.TRANSACTION,), config_version=3)
    result = JevEngine().evaluate(value)
    assert result == JevEngine().evaluate(value)
    assert result.config_version == 3 and result.mode == "SHADOW" and result.ruleset_version == "1"
    assert not result.requires_llm
    allowed = replace(value, policy=ConfigResolver().resolve(replace(value.policy.effective, hosted_ai_allowed=True, auto_rca_draft=True)))
    assert JevEngine().evaluate(allowed).requires_llm
    assert "provider" not in result.__dataclass_fields__


def test_mapping_never_copies_title_or_evidence_summary():
    value = active()
    incident = Incident("incident", "INC-1", "고객 원문", value.severity, value.incident_status,
        "store", "owner", value.occurred_at.isoformat(), value.occurred_at.isoformat())
    mapped = build_context(incident, value.policy, 0)
    assert "title" not in mapped.__dataclass_fields__
    assert mapped.known_evidence_types == ()
