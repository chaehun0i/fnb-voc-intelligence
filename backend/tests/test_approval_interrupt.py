from contextlib import contextmanager
from unittest.mock import Mock

from src.runtime.workflows.checkpoint import memory_checkpoint
from src.runtime.workflows.processor import HistoryProcessor
from tests.test_capa_application import prepared


def test_real_interrupt_durable_wait_and_duplicate_original_delivery():
    p, run, state, job, _ = prepared()
    with p.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"iteration": 1, "rca_completed": True})}))
    saver = memory_checkpoint()
    @contextmanager
    def factory():
        yield saver
    search = Mock()
    processor = HistoryProcessor(p, search, factory, clock=lambda: run.started_at)
    waiting = processor(job)
    assert waiting.status == "WAITING_APPROVAL" and waiting.completed_at is None
    assert processor(job) == waiting
    search.search.assert_not_called()
    graph_state = saver.get_tuple({"configurable": {"thread_id": run.workflow_id}})
    assert graph_state is not None
    with p.transaction("t") as uow:
        assert len(uow.approvals.list()) == 1
        assert not uow.incidents.get("i").approved
        assert uow.agent_runs.steps(run.agent_run_id)[-1].node_name == "approval_interrupt"
