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
    item = intent(payload_json='{"evidence_refs":["review:one"]}', input_references=("review:one",))
    result = asyncio.run(NodeRuntime(Gateway()).execute(item, None, template="Summarize supplied references only."))
    assert result.provider == "fake" and provider.call_count == 1
    with pytest.raises(ValueError):
        asyncio.run(NodeRuntime(Gateway()).execute(item.model_copy(update={"payload_json": '{"raw_voc":"SECRET"}'}),
            None, template="Summarize supplied references only."))
    assert provider.call_count == 1
