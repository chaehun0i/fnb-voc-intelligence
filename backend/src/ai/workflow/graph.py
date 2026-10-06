"""ai/workflow/graph: 통합된 기능 책임, 기존 실행 계약 유지."""
from time import perf_counter
from typing import Annotated, TypedDict
from uuid import NAMESPACE_URL, uuid5

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from src.ai.workflow.models import (
    AgentContextPack,
    InvestigationResult,
    WorkflowState,
    WorkflowStatus,
)


def merge_branches(previous, incoming):
    result = dict(previous)
    for key, value in incoming.items():
        if key in result and result[key] != value:
            raise ValueError("BRANCH_RESULT_CONFLICT")
        result[key] = value
    return dict(sorted(result.items()))


class GraphState(TypedDict):
    snapshot: dict
    branches: Annotated[dict, merge_branches]


def history_graph(checkpointer, investigate, persist, *, observe=None,
                  normalize=None, evaluate=None, rca=None, capa=None, apply_capa=None,
                  request_approval=None, approval_result=None, internal_execution=None,
                  begin_verification=None, verification=None, apply_verification=None,
                  investigate_branch=None, fan_in=None):
    if any(action is not None for action in (normalize, evaluate, rca)) and not all(
            callable(action) for action in (normalize, evaluate, rca)):
        raise ValueError("Evidence 단계는 모두 명시적으로 연결해야 합니다.")
    if capa is not None and not all(callable(a) for a in (normalize, evaluate, rca, apply_capa, request_approval, approval_result)):
        raise ValueError("CAPA 단계는 Application 승인 경계까지 연결해야 합니다.")
    if internal_execution is not None and (capa is None or not all(callable(a) for a in
            (begin_verification, verification, apply_verification))):
        raise ValueError("내부 실행은 Verification Application 경계까지 연결해야 합니다.")
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

    def await_human(value):
        state = WorkflowState.model_validate(value["snapshot"])
        if state.approval is None:
            raise ValueError("APPROVAL_REQUIRED")
        if observe:
            observe("approval_interrupt", state, state, 0)
        # 재실행 가능한 순수 중단 노드: 승인 생성/외부 write를 포함하지 않습니다.
        signal = interrupt({"approval_id": state.approval.approval_id,
            "action_ids": list(state.approval.action_ids), "action_digest": state.approval.action_digest,
            "config_version": state.config_version, "mode": "HUMAN_REVIEW_REQUIRED"})
        if signal != {"approval_id": state.approval.approval_id}:
            raise ValueError("INVALID_RESUME_SIGNAL")
        return {"snapshot": state.model_dump(mode="json")}

    builder = StateGraph(GraphState)
    builder.add_node("validate_context", node("validate_context", lambda state: state))
    if investigate_branch is None:
        builder.add_node("history_investigation", node("history_investigation", investigate))
    builder.add_node("persist_result", node("persist_result", complete))
    builder.add_edge(START, "validate_context")
    if investigate_branch is not None:
        if fan_in is None:
            raise ValueError("INVESTIGATION_FAN_IN_REQUIRED")
        def dispatch(value):
            state = WorkflowState.model_validate(value["snapshot"])
            return [Send("investigate_branch", {"context": c.model_dump(mode="json"),
                "branch_id": str(uuid5(NAMESPACE_URL, state.agent_run_id+":"+c.agent_type))})
                for c in state.contexts] or "history_investigation"

        def branch(value):
            context = AgentContextPack.model_validate(value["context"])
            result = InvestigationResult.model_validate(investigate_branch(context, value["branch_id"]).model_dump(mode="json"))
            if result.agent_type != context.agent_type or result.branch_id != value["branch_id"]:
                raise ValueError("BRANCH_IDENTITY_INVALID")
            return {"branches": {context.agent_type: result.model_dump(mode="json")}}

        def collect(value):
            state = WorkflowState.model_validate(value["snapshot"])
            results = tuple(InvestigationResult.model_validate(v) for _, v in sorted(value.get("branches", {}).items()))
            state = WorkflowState.model_validate(state.model_copy(update={"branches": results}).model_dump(mode="json"))
            result = WorkflowState.model_validate(fan_in(state).model_dump(mode="json"))
            return {"snapshot": result.model_dump(mode="json")}

        # 동일 downstream topology를 사용하며 단일 History 경로는 변경하지 않습니다.
        builder.add_node("investigate_branch", branch)
        builder.add_node("history_investigation", collect)
        builder.add_conditional_edges("validate_context", dispatch, ["investigate_branch", "history_investigation"])
        builder.add_edge("investigate_branch", "history_investigation")
    else:
        builder.add_edge("validate_context", "history_investigation")
    if normalize is not None:
        builder.add_node("normalize_evidence", node("normalize_evidence", normalize))
        builder.add_node("evaluate_sufficiency", node("evaluate_sufficiency", evaluate))
        builder.add_node("rca_investigation", node("rca_investigation", rca))
        builder.add_edge("history_investigation", "normalize_evidence")
        builder.add_edge("normalize_evidence", "evaluate_sufficiency")
        builder.add_conditional_edges("evaluate_sufficiency", lambda value:
            "rca_investigation" if WorkflowState.model_validate(value["snapshot"]).sufficiency.allows_rca
            else "persist_result", ["rca_investigation", "persist_result"])
        if capa is not None:
            for name, action in (("capa_proposal", capa), ("apply_capa", apply_capa),
                                 ("request_approval", request_approval), ("approval_result", approval_result)):
                builder.add_node(name, node(name, action))
            builder.add_node("approval_interrupt", await_human)
            builder.add_edge("rca_investigation", "capa_proposal")
            builder.add_conditional_edges("capa_proposal", lambda value:
                "apply_capa" if WorkflowState.model_validate(value["snapshot"]).capa_proposals
                else "persist_result", ["apply_capa", "persist_result"])
            builder.add_edge("apply_capa", "request_approval")
            builder.add_edge("request_approval", "approval_interrupt")
            builder.add_edge("approval_interrupt", "approval_result")
            if internal_execution is not None:
                for name, action in (("internal_execution", internal_execution), ("begin_verification", begin_verification),
                        ("verification", verification), ("apply_verification", apply_verification)):
                    builder.add_node(name, node(name, action))
                builder.add_conditional_edges("approval_result", lambda value:
                    "internal_execution" if WorkflowState.model_validate(value["snapshot"]).approval.phase == "READY_TO_EXECUTE"
                    else "persist_result", ["internal_execution", "persist_result"])
                builder.add_edge("internal_execution", "begin_verification")
                builder.add_edge("begin_verification", "verification")
                builder.add_edge("verification", "apply_verification")
                builder.add_edge("apply_verification", "persist_result")
            else:
                builder.add_edge("approval_result", "persist_result")
        else:
            builder.add_edge("rca_investigation", "persist_result")
    else:
        builder.add_edge("history_investigation", "persist_result")
    builder.add_edge("persist_result", END)
    return builder.compile(checkpointer=checkpointer)


def invoke_or_resume(graph, state, *, approval_id=None):
    # v4 단일 경로의 15개 노드 + START/END를 완료할 수 있는 bounded 상한입니다.
    config = {"configurable": {"thread_id": state.workflow_id}, "recursion_limit": 20}
    checkpoint = graph.get_state(config)
    restored = WorkflowState.model_validate(checkpoint.values["snapshot"]) if checkpoint.values else None
    if restored and not checkpoint.next and restored.status == WorkflowStatus.COMPLETED:
        return restored
    # pending writes만 남은 중단 상태를 완료로 오인하지 않습니다.
    # 다음 노드가 없고 결과가 미완료라면 같은 실행을 재개하고 영속 메모를 재사용합니다.
    value = None if checkpoint.values and checkpoint.next else {
        "snapshot": (restored or state).model_dump(mode="json")}
    if approval_id is not None:
        if not restored or not restored.approval or restored.approval.approval_id != approval_id:
            raise ValueError("APPROVAL_CHECKPOINT_MISMATCH")
        value = Command(resume={"approval_id": approval_id})
    result = graph.invoke(value, config, durability="sync")
    return WorkflowState.model_validate(result["snapshot"])
