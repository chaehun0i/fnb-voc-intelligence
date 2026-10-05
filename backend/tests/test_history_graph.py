"""단일 Graph가 저장된 단계에서 복구되는지 확인합니다."""
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.domain.workflows.models import WorkflowState, WorkflowStatus
from src.runtime.workflows.checkpoint import SafeJsonSerializer, memory_checkpoint
from src.runtime.workflows.graph import history_graph, invoke_or_resume


def state_example():
    return WorkflowState(tenant_id="a", incident_id="incident", workflow_id=str(uuid4()),
        agent_run_id=str(uuid4()), risk_level="MEDIUM", route="GENERAL_INVESTIGATION", config_version=1)


def test_compile_checkpoint_restore_without_duplicate_node():
    state = state_example()
    saver = memory_checkpoint()
    investigate = Mock(side_effect=lambda value: value.model_copy(update={"iteration": 1}))
    first = invoke_or_resume(history_graph(saver, investigate, lambda _: None), state)
    restored = invoke_or_resume(history_graph(saver, investigate, lambda _: None), state)
    assert first == restored and first.status == "COMPLETED"
    assert investigate.call_count == 1


def test_failure_resumes_pending_node():
    state = state_example()
    saver = memory_checkpoint()
    failing = Mock(side_effect=RuntimeError("실패 주입"))
    with pytest.raises(RuntimeError):
        invoke_or_resume(history_graph(saver, failing, lambda _: None), state)
    restored = invoke_or_resume(history_graph(saver, lambda value: value, lambda _: None), state)
    assert restored.status == "COMPLETED"


def test_serializer_never_revives_classes():
    serde = SafeJsonSerializer()
    value = {"type": "constructor", "id": ["os", "system"]}
    assert serde.loads_typed(serde.dumps_typed(value)) == value
    with pytest.raises(ValueError):
        serde.loads_typed(("pickle", b"payload"))


def test_checkpoint_without_next_is_not_completed_until_state_is_completed():
    state = state_example()
    graph = Mock()
    graph.get_state.return_value = Mock(values={"snapshot": state.model_dump(mode="json")}, next=())
    completed = state.model_copy(update={"status": WorkflowStatus.COMPLETED})
    graph.invoke.return_value = {"snapshot": completed.model_dump(mode="json")}
    assert invoke_or_resume(graph, state) == completed
    assert graph.invoke.call_args.args[0] == {"snapshot": state.model_dump(mode="json")}
    assert graph.invoke.call_args.kwargs["durability"] == "sync"
