"""RCA 제안에는 검증된 출처가 필수입니다."""
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from src.ai.intelligence.models import LLMError, LLMErrorCode, LLMResult, LLMUsage
from src.ai.workflow.agents import RCAInvestigation, validate_candidate
from src.ai.workflow.models import RCACandidate
from src.ai.workflow.policy import evaluate_sufficiency
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from tests.test_evidence_sufficiency import support
from tests.test_history_investigation import state


def ready():
    initial = state()
    items = tuple(s.model_copy(update={"tenant_id": initial.tenant_id, "agent_run_id": initial.agent_run_id})
                  for s in (support(), support("r2")))
    return initial.model_copy(update={"normalized_evidence": items, "sufficiency": evaluate_sufficiency(items)})


def node(**kwargs):
    return RCAInvestigation(ConfigResolver().resolve(replace(RuntimeConfig(), auto_rca_draft=True)),
        "decision", requires_llm=False, clock=lambda: datetime(2026, 10, 6, tzinfo=UTC), **kwargs)


def test_grounded_deterministic_candidate():
    value = ready()
    result = node()(value)
    assert result == node()(value) and result.rca_candidates[0].supporting_refs == ("review:r1", "review:r2")
    assert result.rca_candidates[0].provenance == "HISTORY_HYPOTHESIS_NOT_CONFIRMED"
    assert result.token_spent == 0


def test_no_evidence_no_candidate_and_bad_refs_rejected():
    assert not node()(state()).rca_candidates
    candidate = node()(ready()).rca_candidates[0]
    with pytest.raises(ValueError):
        validate_candidate(candidate.model_copy(update={"supporting_refs": ("review:missing",)}), ready().normalized_evidence)
    with pytest.raises(ValidationError):
        RCACandidate(**{**candidate.model_dump(), "supporting_refs": ()})


@pytest.mark.parametrize("code", [LLMErrorCode.POLICY_DENIED, LLMErrorCode.PROVIDER_UNAVAILABLE, LLMErrorCode.OUTPUT_SCHEMA_INVALID])
def test_gateway_failures_do_not_invent_rca(code):
    executor = Mock(execute=AsyncMock(side_effect=LLMError(code)))
    engine = node(executor=executor)
    engine.requires_llm = True
    initial = ready()
    result = engine(initial)
    assert not result.rca_candidates and result.normalized_evidence == initial.normalized_evidence
    assert result.evidence_gaps


@pytest.mark.parametrize("payload", ['not-json', '{"code":"invented","supporting_refs":[],"confidence":2}',
    '{"code":"REPEATED_HISTORY_SIGNAL","supporting_refs":["review:missing"],"confidence":0.5}'])
def test_invalid_structured_result_cannot_create_candidate(payload):
    initial = ready()
    executor = Mock(execute=AsyncMock(return_value=LLMResult(request_id="fake", provider="fake", model="fake",
        config_version=initial.config_version, structured_json=payload, usage=LLMUsage())))
    engine = node(executor=executor)
    engine.requires_llm = True
    result = engine(initial)
    assert not result.rca_candidates and result.normalized_evidence == initial.normalized_evidence
    assert executor.execute.call_count == 1 and result.evidence_gaps


def test_rca_obeys_pinned_run_deadline_without_call():
    executor = Mock(execute=AsyncMock())
    engine = node(executor=executor, deadline=datetime(2026, 10, 5, tzinfo=UTC))
    engine.requires_llm = True
    result = engine(ready())
    assert not result.rca_candidates and result.evidence_gaps[-1].code == "RCA_BUDGET_EXHAUSTED"
    executor.execute.assert_not_called()
