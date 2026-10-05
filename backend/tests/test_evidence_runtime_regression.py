"""RCA 외부 효과와 durable 결과의 중단·중복·정책 실패 의미를 고정합니다."""
import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.application.decisions.shadow import ShadowDecisions
from src.domain.jobs.models import Job
from src.domain.workflows.models import EvidenceCandidate
from src.infrastructure.queue.worker import RetryableJobError
from src.llm.contracts import LLMResult, LLMUsage
from src.llm.errors import LLMError, LLMErrorCode
from src.runtime.workflows.checkpoint import SafeJsonSerializer, memory_checkpoint
from src.runtime.workflows.processor import HistoryProcessor, UncertainHistoryCall


class ScopedSearch:
    def __init__(self):
        self.calls = 0

    def search_evidence(self, tenant, store, query):
        self.calls += 1
        return [EvidenceCandidate(source_ref="review:r"+str(rank), rank=rank,
            retrieved_at=datetime(2026, 10, 6, tzinfo=UTC), tenant_id=tenant, store=store,
            provenance=("lexical",), stance="SUPPORTING", observation_code="RELATED_HISTORY_MATCH")
            for rank in (1, 2)]


def prepare(history_setup):
    persistence, service, context, _ = history_setup
    with persistence.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1,
            config=replace(version.config, auto_rca_draft=True, hosted_ai_allowed=True)), 1)
    now = datetime.now(UTC)
    service.clock = lambda: now
    decision = ShadowDecisions(persistence).record(Job("rca-snapshot", "t", "incident.snapshot", "correlation",
        now, now, incident_id="i", store="store"))
    assert decision.result.requires_llm
    return persistence, service.enqueue(context, "i", decision.decision_id)


def output(value):
    return LLMResult(request_id="fake", provider="fake", model="fake", config_version=2,
                     structured_json=json.dumps(value), usage=LLMUsage(input_tokens=10, output_tokens=5))


def outputs():
    return [output({"needs_more_history": False}), output({"code": "REPEATED_HISTORY_SIGNAL",
        "supporting_refs": ["review:r1", "review:r2"], "confidence": .5})]


class FailAfterRCA(InMemorySaver):
    def __init__(self):
        super().__init__(serde=SafeJsonSerializer())
        self.failed = False

    def put(self, config, checkpoint, metadata, new_versions):
        state = checkpoint.get("channel_values", {}).get("snapshot", {})
        if state.get("rca_completed") and state.get("status") == "RUNNING" and not self.failed:
            self.failed = True
            raise psycopg.OperationalError("checkpoint fault")
        return super().put(config, checkpoint, metadata, new_versions)


def processor(persistence, search, saver, executor):
    @contextmanager
    def checkpoint():
        yield saver
    return HistoryProcessor(persistence, search, checkpoint, executor_factory=lambda _: executor)


def test_rca_checkpoint_failure_reuses_result_without_provider_replay(history_setup):
    persistence, job = prepare(history_setup)
    search, saver = ScopedSearch(), FailAfterRCA()
    executor = Mock(execute=AsyncMock(side_effect=outputs()))
    original = persistence.incidents.get("i")
    with pytest.raises(RetryableJobError):
        processor(persistence, search, saver, executor)(job)
    with persistence.transaction("t") as uow:
        failed = uow.agent_runs.by_job(job.job_id)
        assert failed.state.rca_completed and len(failed.state.rca_candidates) == 1
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=3, parent_version=2,
            config=replace(version.config, auto_rca_draft=False)), 2)
    result = processor(persistence, search, saver, executor)(job)
    assert result.status == "COMPLETED" and result.config_version == 2 and result.state.token_spent == 30
    assert executor.execute.call_count == 2 and search.calls == 1
    assert processor(persistence, search, saver, executor)(job) == result
    assert persistence.incidents.get("i") == original


def test_uncertain_rca_effect_is_not_called_again(history_setup):
    persistence, job = prepare(history_setup)
    executor = Mock(execute=AsyncMock(side_effect=[outputs()[0], RuntimeError("uncertain-provider-effect")]))
    engine = processor(persistence, ScopedSearch(), memory_checkpoint(), executor)
    original = persistence.incidents.get("i")
    with pytest.raises(RuntimeError):
        engine(job)
    with pytest.raises(UncertainHistoryCall):
        engine(job)
    assert executor.execute.call_count == 2 and persistence.incidents.get("i") == original


@pytest.mark.parametrize("failure", [LLMErrorCode.POLICY_DENIED, LLMErrorCode.PROVIDER_UNAVAILABLE,
                                   LLMErrorCode.OUTPUT_SCHEMA_INVALID])
def test_history_llm_failure_preserves_evidence_but_never_forces_rca(history_setup, failure):
    persistence, job = prepare(history_setup)
    executor = Mock(execute=AsyncMock(side_effect=LLMError(failure)))
    result = processor(persistence, ScopedSearch(), memory_checkpoint(), executor)(job)
    assert result.state.sufficiency.status == "SUFFICIENT"
    assert len(result.state.normalized_evidence) == 2 and not result.state.rca_candidates
    assert executor.execute.call_count == 1 and result.state.evidence_gaps


def test_legacy_history_v1_still_has_only_original_nodes(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    run, _, _ = service.prepare(job)
    # 이전 영속 레코드의 버전을 fixture에서 복원합니다. 실제 저장소 불변성은 우회하지 않습니다.
    persistence.memory.data["agent_runs"][run.agent_run_id] = run.model_copy(update={"workflow_version": "history-v1"})
    result = processor(persistence, ScopedSearch(), memory_checkpoint(), None)(job)
    with persistence.transaction("t") as uow:
        assert [s.node_name for s in uow.agent_runs.steps(result.agent_run_id)] == [
            "validate_context", "history_investigation", "persist_result"]
    assert result.state.sufficiency is None and not result.state.rca_candidates
