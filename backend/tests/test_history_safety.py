"""실행·정책·복구·예산·출처 경계의 실패 경로를 확인합니다."""
import ast
import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from src.application.incidents.service import IncidentNotFound
from src.application.security.principal import AccessError, Role
from src.application.workflows.history import WorkflowNotAllowed, validate_start
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver
from src.domain.workflows.models import Finding, WorkflowState
from src.llm.errors import LLMError, LLMErrorCode
from src.rag.lexical_search import search_reviews_lexically
from src.rag.search_models import SearchFilters
from src.rag.vector_search import search_similar_reviews
from src.runtime.workflows.checkpoint import memory_checkpoint
from src.runtime.workflows.history import HistoryInvestigation
from src.runtime.workflows.processor import HistoryProcessor, UncertainHistoryCall


@pytest.mark.parametrize("change", [{"auto_investigation": False}, {"jev_enabled": False},
                                  {"allowed_agent_types": ()}, {"allowed_tools": ()}])
def test_policy_opt_in_is_required(history_setup, change):
    persistence, _, _, decision = history_setup
    with persistence.transaction("t") as uow:
        incident, version = uow.incidents.get("i"), uow.configs.current()
        with pytest.raises(WorkflowNotAllowed):
            validate_start(incident, decision, replace(version, config=replace(version.config, **change)))


@pytest.mark.parametrize("change", [{"investigation_agents": ()}, {"route": "MANUAL_REVIEW"},
                                  {"workflow_profile": "unsupported"}, {"config_version": 99}])
def test_decision_gate(history_setup, change):
    persistence, _, _, decision = history_setup
    with persistence.transaction("t") as uow, pytest.raises(WorkflowNotAllowed):
        validate_start(uow.incidents.get("i"), replace(decision, result=replace(decision.result, **change)), uow.configs.current())


def test_role_and_tenant_start_denied(history_setup):
    _, service, context, decision = history_setup
    with pytest.raises(AccessError):
        service.enqueue(replace(context, principal=replace(context.principal, roles=frozenset({Role.AUDITOR}))), "i", decision.decision_id)
    with pytest.raises(IncidentNotFound):
        service.enqueue(replace(context, principal=replace(context.principal, tenant_id="other")), "i", decision.decision_id)


@pytest.mark.parametrize("field", ["credential", "raw_prompt", "raw_response", "customer_name", "access_token"])
def test_sensitive_state_and_findings_rejected(history_setup, field):
    _, service, context, decision = history_setup
    run, _, _ = service.prepare(service.enqueue(context, "i", decision.decision_id))
    with pytest.raises(ValidationError):
        WorkflowState.model_validate({**run.state.model_dump(), field: "PII-SENTINEL"})
    with pytest.raises(ValidationError):
        Finding(evidence_refs=("review:r1",), **{field: "PII-SENTINEL"})


def test_llm_policy_denied_keeps_retrieval_refs(history_setup):
    _, service, context, decision = history_setup
    run, resolved, _ = service.prepare(service.enqueue(context, "i", decision.decision_id))
    search, executor = Mock(), Mock()
    search.search.return_value = [("review:r1", 1)]
    executor.execute = AsyncMock(side_effect=LLMError(LLMErrorCode.POLICY_DENIED))
    result = HistoryInvestigation(search, store="store", query="PII-SENTINEL",
        resolved=resolved, requires_llm=True, executor=executor,
        clock=lambda: datetime(2026, 10, 5, tzinfo=UTC))(run.state)
    assert result.evidence_refs == ("review:r1",) and result.evidence_gaps[0].code == "LLM_POLICY_DENIED"
    intent = executor.execute.call_args.args[0]
    assert "PII-SENTINEL" not in intent.payload_json and json.loads(intent.payload_json)["evidence_count"] == 1


def test_tool_budget_and_iteration_limit(history_setup):
    _, service, context, decision = history_setup
    run, _, _ = service.prepare(service.enqueue(context, "i", decision.decision_id))
    search = Mock()
    node = HistoryInvestigation(search, store="store", query="quality",
        resolved=ConfigResolver().resolve(RuntimeConfig(max_tool_calls=1, max_agent_iterations=1)),
        requires_llm=False, clock=lambda: datetime(2026, 10, 5, tzinfo=UTC))
    for state in (run.state.model_copy(update={"tool_call_count": 1}), run.state.model_copy(update={"iteration": 1})):
        with pytest.raises(ValueError):
            node(state)
    search.search.assert_not_called()


def test_uncertain_llm_is_not_reexecuted_and_incident_unchanged(history_setup):
    persistence, service, context, decision = history_setup
    with persistence.transaction("t") as uow:
        # 결정 원본은 fixture에서만 교체하고 실제 불변 DB는 변경하지 않습니다.
        key = ("t", "snapshot", "1")
        uow.decisions.state.data["decisions"][key] = replace(decision, result=replace(decision.result, requires_llm=True))
    job = service.enqueue(context, "i", decision.decision_id)
    search, executor = Mock(), Mock()
    search.search.return_value = [("review:r1", 1)]
    executor.execute = AsyncMock(side_effect=RuntimeError("PII-SENTINEL"))
    saver = memory_checkpoint()
    @contextmanager
    def checkpoint():
        yield saver
    processor = HistoryProcessor(persistence, search, checkpoint, executor_factory=lambda _: executor)
    original = persistence.incidents.get("i")
    with pytest.raises(RuntimeError):
        processor(job)
    with pytest.raises(UncertainHistoryCall):
        processor(job)
    assert executor.execute.call_count == 1 and persistence.incidents.get("i") == original
    with persistence.transaction("t") as uow:
        run = uow.agent_runs.by_job(job.job_id)
        assert run.status == "FAILED" and run.error_code == "WORKFLOW_FAILED"
        assert "PII-SENTINEL" not in run.model_dump_json()


def test_search_scope_is_in_both_sql_modes():
    filters = SearchFilters(tenant_id="tenant-a", store="store-a")
    cursor = Mock()
    cursor.fetchall.return_value = []
    search_reviews_lexically(cursor, "quality", filters=filters)
    sql, args = cursor.execute.call_args.args
    assert "serviq_history_sources" in sql and "tenant-a" in args and "store-a" in args
    search_similar_reviews(cursor, [1.0, 0.0], "fake", filters=filters)
    sql, args = cursor.execute.call_args.args
    assert "serviq_history_sources" in sql and "tenant-a" in args and "store-a" in args
    with pytest.raises(ValidationError):
        SearchFilters(tenant_id="tenant-a")


def test_domain_jev_and_history_never_import_provider_sdk():
    source = Path(__file__).parents[1]/"src"
    files = list((source/"domain").rglob("*.py"))
    files += list((source/"runtime/workflows").rglob("*.py"))
    files += list((source/"application/workflows").rglob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(name.startswith(("google", "ollama", "src.llm.providers")) for name in modules), path
