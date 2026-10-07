import json

import pytest
from pydantic import ValidationError

from src.ai.execution.tools import READ_TOOLS, ToolContract, ToolInput, ToolRegistry


def test_registry_is_versioned_immutable_and_unique():
    assert READ_TOOLS.version == "read-tools-1"
    assert len(READ_TOOLS.contracts()) == 4
    contract = READ_TOOLS.resolve("get_inventory")
    with pytest.raises(ValidationError):
        contract.risk_level = "HIGH"
    with pytest.raises(ValueError, match="TOOL_DUPLICATE"):
        ToolRegistry((contract, contract))


@pytest.mark.parametrize("name,version", [("shell", "1"), ("get_inventory", "2")])
def test_unknown_tool_or_version_fails_closed(name, version):
    with pytest.raises(ValueError, match="TOOL_UNKNOWN"):
        READ_TOOLS.resolve(name, version)


def test_tool_schema_is_canonical_and_rejects_scope_or_unbounded_input():
    contract = READ_TOOLS.resolve("get_incident")
    assert json.loads(contract.input_schema_json) == ToolInput.model_json_schema()
    with pytest.raises(ValidationError):
        ToolContract.model_validate({**contract.model_dump(), "input_schema_json": "{}"})
    for extra in ({"tenant_id": "other"}, {"actor_id": "admin"}, {"limit": 21}):
        with pytest.raises(ValidationError):
            ToolInput(incident_id="a"*36, **extra)


def test_errors_and_ax_are_machine_readable_without_raw_exception():
    from src.ai.execution.tools import ERRORS, ToolFailure, tool_error
    for code in ERRORS:
        error = tool_error(code)
        assert str(ToolFailure(error)) == code
        assert error.safe_message and error.suggested_action
        assert error.retryable == (error.category == "TOOL_TEMPORARY")
        assert "password" not in error.model_dump_json()
    for contract in READ_TOOLS.contracts():
        assert contract.when_to_use and contract.when_not_to_use and contract.preconditions
        assert "NO_DATA" in contract.common_errors
        assert "NO_RETRY_ON_AUTH" in contract.retry_guidance


def query_setup():
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from src.ai.workflow.models import OperationalObservation
    from src.ai.workflow.policy import build_context
    from src.application.incidents.service import IncidentService
    from src.application.security.principal import Principal, Role
    from src.infrastructure.investigation_source import MemoryInvestigationSource
    from tests.test_data_intake import client
    persistence = client().app.state.access_persistence
    principal = Principal("operator", "a", frozenset({Role.HQ_ADMIN}))
    now = datetime.now(UTC)
    with persistence.transaction("a") as uow:
        item = IncidentService(uow.incidents, principal=principal).create("품질", "MEDIUM", "매장", "operator")
        other = IncidentService(uow.incidents, principal=principal).create("유사 사례", "MEDIUM", "매장", "operator")
    observations = tuple(OperationalObservation(tenant_id="a", store="매장", agent_type=agent,
        source_ref=agent.lower()+":"+str(uuid4()), observed_at=now,
        signal="REFUND_SIGNAL" if agent == "TRANSACTION" else "STOCK_SHORTAGE")
        for agent in ("TRANSACTION", "INVENTORY"))
    source = MemoryInvestigationSource(observations, history_available=True)
    contexts = tuple(build_context(agent, tenant_id="a", incident_id=item.id, store="매장",
        category="GENERAL", severity="MEDIUM", window_start=now-timedelta(hours=1),
        window_end=now, now=now) for agent in ("HISTORY", "TRANSACTION", "INVENTORY"))
    return persistence, source, principal, item, other, contexts, now


def test_four_business_queries_are_bounded_reference_only_and_scoped():
    from src.application.incidents.service import IncidentNotFound
    from src.application.security.principal import AccessError, Principal, Role
    from src.application.tool_queries import BusinessToolQueries
    p, source, principal, incident, _, packs, _ = query_setup()
    queries = BusinessToolQueries(p, source)
    for name, pack in zip(("get_incident", "search_similar_incidents", "get_transactions", "get_inventory"), (packs[0], packs[0], packs[1], packs[2]), strict=True):
        result = queries.read(name, ToolInput(incident_id=incident.id, limit=1), principal=principal, context=pack)
        assert result.items and len(result.items) == 1
        assert "품질" not in result.model_dump_json()
        assert "tenant_id" not in result.model_dump_json()
    with pytest.raises(IncidentNotFound):
        queries.read("get_incident", ToolInput(incident_id="0"*36), principal=principal, context=packs[0])
    with pytest.raises(AccessError):
        queries.read("get_inventory", ToolInput(incident_id=incident.id), principal=principal,
            context=packs[2].model_copy(update={"tenant_id": "other"}))
    restricted = Principal("store", "a", frozenset({Role.STORE_MANAGER}), frozenset({"다른 매장"}))
    with pytest.raises(AccessError):
        queries.read("get_incident", ToolInput(incident_id=incident.id), principal=restricted, context=packs[0])


def test_tool_harness_rechecks_policy_scope_and_reuses_receipt():
    from src.ai.execution.runtime import ToolHarness
    from src.ai.execution.tools import ToolFailure
    from tests.test_loop_harness import loop_setup
    p, source, run, now = loop_setup()
    harness = ToolHarness(p, source, tenant_id="t", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    args = {"incident_id": run.incident_id, "limit": 1}
    result = harness.execute("get_transactions", args)
    assert result.tool_name == "get_transactions"
    assert harness.execute("get_transactions", args) == result
    with p.transaction("t") as uow:
        saved = uow.agent_runs.get(run.agent_run_id)
        assert saved.state.tool_call_count == 1 and len(saved.state.tool_calls) == 1
    with pytest.raises(ToolFailure):
        harness.execute("shell", args)
    with pytest.raises(ToolFailure):
        harness.execute("get_transactions", args | {"tenant_id": "other"})


def test_langchain_composition_executes_only_through_gateway():
    import asyncio

    from src.ai.intelligence.node import NodeRuntime
    from src.ai.intelligence.providers.fake import FakeProvider
    from src.ai.intelligence.service import LLMGateway
    from tests.test_llm_contracts import intent
    provider = FakeProvider()
    class Gateway:
        async def execute(self, item, resolved, **kwargs):
            assert '"messages"' in item.payload_json
            assert item.input_references == ("review:one",)
            return await LLMGateway(provider).execute(item, model="fake-v1", **kwargs)
    item = intent(payload_json='{"evidence_refs":["review:one"]}', input_references=("review:one",),
        prompt_template="reference-summary", schema_version="history-1")
    result = asyncio.run(NodeRuntime(Gateway()).execute(item, None))
    assert result.provider == "fake" and provider.call_count == 1
    with pytest.raises(ValueError):
        asyncio.run(NodeRuntime(Gateway()).execute(item.model_copy(update={"payload_json": '{"raw_voc":"SECRET"}'}),
            None))
    assert provider.call_count == 1


def test_prompt_resolution_digest_and_inactive_fail_closed():
    from src.ai.intelligence.prompts import PROMPTS, PromptRegistry
    p = PROMPTS.resolve("observation-lookup")
    assert p.reference() == PROMPTS.resolve(p.prompt_id).reference()
    assert len(p.reference().digest) == 64
    assert "template" not in p.reference().model_dump()
    with pytest.raises(ValueError):
        PROMPTS.resolve("unknown")
    with pytest.raises(ValueError):
        PromptRegistry((p, p))
    with pytest.raises(ValueError):
        PromptRegistry((p.model_copy(update={"status": "INACTIVE"}),)).resolve(p.prompt_id)


def test_official_mcp_client_schema_and_safe_protocol_errors():
    import asyncio

    from mcp import Client

    from src.ai.execution.tools import ToolResult
    from src.mcp.server import ReadToolServer
    class BoundHarness:
        def execute(self, name, arguments):
            if arguments["incident_id"] == "failure":
                raise RuntimeError("password=SECRET raw SQL")
            return ToolResult(tool_name=name)
    async def check():
        async with Client(ReadToolServer(BoundHarness())) as client:
            listed = await client.list_tools()
            assert len(listed.tools) == 4
            for t in listed.tools:
                expected = READ_TOOLS.resolve(t.name)
                assert t.input_schema == json.loads(expected.input_schema_json)
                assert t.output_schema == json.loads(expected.output_schema_json)
            result = await client.call_tool("get_incident", {"incident_id": "safe"})
            assert not result.is_error and result.structured_content["tool_name"] == "get_incident"
            for name, args in (("shell", {}), ("get_incident", {"incident_id": "safe", "tenant_id": "other"}),
                    ("get_incident", {"incident_id": "failure"})):
                failed = await client.call_tool(name, args)
                assert failed.is_error and "SECRET" not in failed.model_dump_json()
    asyncio.run(check())


def test_tool_agent_vertical_slice_preserves_evidence_and_reuses_completed_work():
    from contextlib import contextmanager
    from unittest.mock import Mock

    from src.ai.ax.service import AgentRunQueries
    from src.ai.workflow.models import EvidenceCandidate
    from src.ai.workflow.runtime import HistoryProcessor, memory_checkpoint
    from src.api.schemas.agent_runs import AgentRunDetailResponse
    from src.application.security.principal import Principal
    from tests.test_multi_agent import NOW, multi_setup
    p, _, source, job = multi_setup(all_agents=True, tool_runtime=True)
    source.observations = Mock(wraps=source.observations)
    class Search:
        def search_evidence(self, *args):
            return tuple(EvidenceCandidate(source_ref="review:"+r, rank=1, tenant_id="t", store="store",
                source_at=NOW, retrieved_at=NOW, observation_code="RELATED_HISTORY_MATCH", stance="SUPPORTING")
                for r in ("one", "two"))
    saver = memory_checkpoint()
    @contextmanager
    def checkpoint():
        yield saver
    processor = HistoryProcessor(p, Search(), checkpoint, source=source, clock=lambda: NOW)
    result = processor(job)
    assert result.state.tool_runtime_enabled and len(result.state.tool_calls) == 2
    assert result.state.tool_call_count == 3  # three real reads, not five double-charged operations.
    assert result.state.sufficiency.allows_rca and result.state.rca_candidates
    assert len(result.state.normalized_evidence) == 4
    assert result.manifest.tool_bundle_versions == ("read-tools-1",)
    assert {r.prompt_id for r in result.manifest.prompt_versions} == {"reference-summary", "observation-lookup", "history-grounded-rca"}
    assert processor(job) == result and source.observations.call_count == 2
    detail = AgentRunQueries(p, Principal("auditor", "t", frozenset({"AUDITOR"}))).execute("i", run_id=result.agent_run_id)
    dto = AgentRunDetailResponse.model_validate(detail).model_dump(mode="json")
    assert len(dto["tools"]) == 2 and all(t["status"] == "COMPLETED" for t in dto["tools"])
    assert "tool_calls" not in dto and "context_digest" not in str(dto)


@pytest.mark.parametrize("control", ["PAUSED", "STOPPED", "MANUAL_TAKEOVER"])
def test_tool_control_recheck_blocks_even_cached_reads(control):
    from src.ai.execution.runtime import ToolHarness
    from src.ai.execution.tools import ToolFailure
    from src.ai.workflow.models import RuntimeEvent
    from tests.test_loop_harness import loop_setup
    p, source, run, now = loop_setup()
    harness = ToolHarness(p, source, tenant_id="t", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    args = {"incident_id": run.incident_id}
    harness.execute("get_transactions", args)
    with p.transaction("t") as uow:
        uow.agent_runs.append_event(run.agent_run_id, RuntimeEvent(event_id="control",
            kind="CONTROL", control=control, actor_id="operator", created_at=now))
    with pytest.raises(ToolFailure) as error:
        harness.execute("get_transactions", args)
    assert error.value.error.code == "POLICY_DENIED"


def test_uncertain_tool_claim_never_reexecutes_or_leaks_exception():
    import asyncio
    from unittest.mock import Mock

    from src.ai.execution.runtime import ToolHarness
    from src.ai.execution.tools import ToolFailure
    from src.mcp.server import call_in_memory
    from tests.test_loop_harness import loop_setup
    p, source, run, now = loop_setup()
    source.observations = Mock(side_effect=LookupError("credential=SECRET"))
    harness = ToolHarness(p, source, tenant_id="t", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    for _ in range(2):
        with pytest.raises(ToolFailure) as error:
            asyncio.run(call_in_memory(harness, "get_transactions", {"incident_id": run.incident_id}))
        assert error.value.error.code == "OUTCOME_UNKNOWN" and not error.value.error.retryable
        assert "SECRET" not in str(error.value)
    assert source.observations.call_count == 1


def test_current_capability_budget_and_receipt_immutability():
    from unittest.mock import Mock

    from src.ai.execution.runtime import ToolHarness
    from src.ai.execution.tools import ToolFailure
    from tests.test_loop_harness import loop_setup
    p, source, run, now = loop_setup(max_operations=1)
    harness = ToolHarness(p, source, tenant_id="t", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    args = {"incident_id": run.incident_id, "limit": 1}
    result = harness.execute("get_transactions", args)
    with pytest.raises(ToolFailure) as exhausted:
        harness.execute("get_transactions", args | {"limit": 2})
    assert exhausted.value.error.code == "BUDGET_EXHAUSTED"
    source.capabilities = Mock(return_value=())
    with pytest.raises(ToolFailure) as denied:
        harness.execute("get_transactions", args)
    assert denied.value.error.code == "NO_DATA"
    with p.transaction("t") as uow:
        current = uow.agent_runs.get(run.agent_run_id)
        changed = current.state.tool_calls[0].model_copy(update={"result": result.model_copy(update={"items": ()})})
        with pytest.raises(ValueError, match="IMMUTABLE"):
            uow.agent_runs.save(current.model_copy(update={"state": current.state.model_copy(update={"tool_calls": (changed,)})}))
        with pytest.raises(ValueError, match="IMMUTABLE"):
            uow.agent_runs.save(current.model_copy(update={"state": current.state.model_copy(update={"tool_calls": ()})}))


def test_tool_cross_tenant_and_scope_cannot_be_injected():
    from src.ai.execution.runtime import ToolHarness
    from src.application.incidents.service import IncidentNotFound
    from src.application.security.principal import AccessError
    from tests.test_loop_harness import loop_setup
    p, source, run, now = loop_setup()
    foreign = ToolHarness(p, source, tenant_id="other", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    with pytest.raises(IncidentNotFound):
        foreign.execute("get_transactions", {"incident_id": run.incident_id})
    bound = ToolHarness(p, source, tenant_id="t", run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    with pytest.raises(AccessError):
        bound.execute("get_inventory", {"incident_id": run.incident_id})
    with pytest.raises(TypeError):
        bound.execute("get_transactions", {"incident_id": run.incident_id}, principal="admin")


def test_normalized_tool_output_cannot_carry_unbounded_or_sensitive_payloads():
    from src.ai.execution.tools import ToolItem, ToolResult, tool_error
    with pytest.raises(ValidationError):
        ToolItem(source_ref="transaction:one", source_type="TRANSACTION", source_at="SECRET")
    with pytest.raises(ValidationError):
        ToolItem(source_ref="transaction:one", source_type="TRANSACTION", provenance=("raw credential",))
    item = ToolItem(source_ref="transaction:one", source_type="TRANSACTION")
    with pytest.raises(ValidationError):
        ToolResult(tool_name="get_transactions", items=(item,)*21)
    with pytest.raises(ValidationError):
        type(tool_error("NO_DATA")).model_validate(tool_error("NO_DATA").model_dump() | {"safe_message": "SECRET"})


def test_langchain_malformed_output_preserves_gateway_error_contract():
    import asyncio

    from src.ai.intelligence.models import LLMError, LLMErrorCode
    from src.ai.intelligence.node import NodeRuntime
    from src.ai.intelligence.providers.fake import FakeProvider
    from src.ai.intelligence.service import LLMGateway
    from tests.test_llm_contracts import intent
    class Gateway:
        async def execute(self, item, resolved, **kwargs):
            return await LLMGateway(FakeProvider(["not-json"])).execute(item, model="fake-v1", **kwargs)
    item = intent(payload_json='{"evidence_refs":["review:one"]}', input_references=("review:one",),
        prompt_template="reference-summary", schema_version="history-1")
    with pytest.raises(LLMError) as error:
        asyncio.run(NodeRuntime(Gateway()).execute(item, None))
    assert error.value.code == LLMErrorCode.OUTPUT_SCHEMA_INVALID


def test_actual_rca_node_uses_pinned_composition_and_fake_gateway():
    from datetime import UTC, datetime

    from src.ai.intelligence.providers.fake import FakeProvider
    from src.ai.intelligence.service import LLMGateway
    from tests.test_rca_investigation import node, ready
    provider = FakeProvider(['{"code":"REPEATED_HISTORY_SIGNAL","supporting_refs":["review:r1","review:r2"],"confidence":0.6}'])
    class Gateway:
        async def execute(self, item, resolved, **kwargs):
            assert item.prompt_template == "history-grounded-rca" and item.prompt_version == "1"
            assert '"messages"' in item.payload_json and '"raw_voc"' not in item.payload_json
            return await LLMGateway(provider, clock=lambda: datetime(2026, 10, 6, tzinfo=UTC)).execute(
                item, model="fake-v1", **kwargs)
    engine = node(executor=Gateway())
    engine.requires_llm = True
    result = engine(ready().model_copy(update={"tool_runtime_enabled": True}))
    assert result.rca_candidates[0].generated_by == "LLM_GATEWAY"
    assert provider.call_count == 1 and result.token_spent == 15


def test_imported_tool_evidence_provenance_survives_trace_dto():
    from datetime import UTC, datetime

    from src.ai.execution.tools import ToolItem, ToolResult
    from src.api.schemas.agent_runs import EvidenceCandidateResponse

    item = ToolItem(source_ref="transaction:imported", source_type="TRANSACTION",
        provenance=("file_imported_operational",))
    result = ToolResult(tool_name="get_transactions", items=(item,))
    dto = EvidenceCandidateResponse.model_validate({
        "source_ref": result.items[0].source_ref, "source_type": "TRANSACTION", "rank": 1,
        "retrieved_at": datetime(2026, 10, 7, tzinfo=UTC), "provenance": result.items[0].provenance,
    })
    assert dto.provenance == ["file_imported_operational"]
