"""동기 Checkpoint 저장을 완료한 다음 노드로만 진행합니다."""
from time import perf_counter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.domain.workflows.models import WorkflowState, WorkflowStatus


class GraphState(TypedDict):
    snapshot: dict


def history_graph(checkpointer, investigate, persist, *, observe=None):
    def node(name, action):
        def execute(value):
            state = WorkflowState.model_validate(value["snapshot"])
            started = perf_counter()
            try:
                updated = action(state)
            except Exception:
                if observe:
                    observe(name, state, state, (perf_counter()-started)*1000, failed=True)
                raise
            # 노드 출력도 다시 검증하여 model_copy를 통한 우회를 차단합니다.
            result = WorkflowState.model_validate(updated.model_dump(mode="json"))
            if observe:
                observe(name, state, result, (perf_counter()-started)*1000)
            return {"snapshot": result.model_dump(mode="json")}
        return execute

    def complete(state):
        result = state.model_copy(update={"status": WorkflowStatus.COMPLETED})
        persist(result)
        return result

    builder = StateGraph(GraphState)
    builder.add_node("validate_context", node("validate_context", lambda state: state))
    builder.add_node("history_investigation", node("history_investigation", investigate))
    builder.add_node("persist_result", node("persist_result", complete))
    builder.add_edge(START, "validate_context")
    builder.add_edge("validate_context", "history_investigation")
    builder.add_edge("history_investigation", "persist_result")
    builder.add_edge("persist_result", END)
    return builder.compile(checkpointer=checkpointer)


def invoke_or_resume(graph, state):
    config = {"configurable": {"thread_id": state.workflow_id}, "recursion_limit": 8}
    checkpoint = graph.get_state(config)
    restored = WorkflowState.model_validate(checkpoint.values["snapshot"]) if checkpoint.values else None
    if restored and not checkpoint.next and restored.status == WorkflowStatus.COMPLETED:
        return restored
    # pending writes만 남은 중단 상태를 완료로 오인하지 않습니다.
    # 다음 노드가 없고 결과가 미완료라면 같은 실행을 재개하고 영속 메모를 재사용합니다.
    value = None if checkpoint.values and checkpoint.next else {
        "snapshot": (restored or state).model_dump(mode="json")}
    result = graph.invoke(value, config, durability="sync")
    return WorkflowState.model_validate(result["snapshot"])
