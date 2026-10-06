"""Graph 재전달은 동일 실행/검색 결과를 재사용합니다."""
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

from src.agents.checkpoint import memory_checkpoint
from src.agents.models import WorkflowStatus
from src.agents.processor import HistoryProcessor


def test_processor_duplicate_delivery_and_failure_boundary(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    original = persistence.incidents.get("i")
    search = Mock()
    search.search.return_value = [("review:r1", 1)]
    saver = memory_checkpoint()
    @contextmanager
    def checkpoint():
        yield saver
    processor = HistoryProcessor(persistence, search, checkpoint,
        clock=lambda: datetime(2026, 10, 5, tzinfo=UTC))
    first = processor(job)
    assert first.status == WorkflowStatus.COMPLETED and processor(job) == first
    assert search.search.call_count == 1
    assert persistence.incidents.get("i") == original
    with persistence.transaction("t") as uow:
        steps = uow.agent_runs.steps(first.agent_run_id)
        assert [s.node_name for s in steps] == ["validate_context", "history_investigation",
            "normalize_evidence", "evaluate_sufficiency", "persist_result"]
        assert first.state.sufficiency.status == "INSUFFICIENT"
        assert steps[-1].result == first.state
