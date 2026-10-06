from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.ai.workflow.models import LoopPolicy
from src.ai.workflow.policy import evidence_digest, loop_policy, loop_termination
from src.domain.config.models import RuntimeConfig


def test_loop_policy_uses_server_caps_and_existing_counters():
    policy = loop_policy(RuntimeConfig(max_agent_iterations=20))
    assert policy.max_iterations == 3
    now = datetime.now(UTC)
    state = SimpleNamespace(iteration=1, tool_call_count=3, token_spent=0, cost_spent=0,
        evidence_refs=("review:one",))
    assert loop_termination(policy, state, now=now, started_at=now) is None
    assert loop_termination(policy, state, now=now, started_at=now,
        before_refs=("review:one",)) == "NO_NEW_EVIDENCE"
    state.iteration = 3
    assert loop_termination(policy, state, now=now, started_at=now) == "ITERATION_LIMIT"
    state.tool_call_count = policy.max_operations
    assert loop_termination(policy, state, now=now, started_at=now) == "BUDGET_EXHAUSTED"
    state.tool_call_count = 0
    assert loop_termination(policy, state, now=now+timedelta(seconds=120), started_at=now) == "BUDGET_EXHAUSTED"


@pytest.mark.parametrize("field,value", [("max_iterations", 4), ("max_operations", -1),
    ("token_budget", True), ("cost_budget", float("inf")), ("timeout_seconds", 601)])
def test_invalid_budget_rejected(field, value):
    values = loop_policy(RuntimeConfig()).model_dump()
    with pytest.raises(ValidationError):
        LoopPolicy(**(values | {field: value}))


def test_canonical_evidence_digest_is_order_and_duplicate_independent():
    assert evidence_digest(("review:a", "review:b", "review:a")) == evidence_digest(("review:b", "review:a"))


def test_manifest_snapshot_and_repository_immutability():
    from src.ai.workflow.models import AgentRun
    from src.ai.workflow.policy import run_manifest
    from src.infrastructure.repositories.agent_run_repository import validate
    from tests.test_multi_agent import NOW, workflow
    state = workflow()
    run = AgentRun(agent_run_id=state.agent_run_id, tenant_id=state.tenant_id,
        incident_id=state.incident_id, workflow_id=state.workflow_id, job_id="job-a",
        correlation_id="correlation-a", config_version=state.config_version,
        jev_decision_id="decision-a", started_at=NOW, state=state)
    run = AgentRun.model_validate(run.model_copy(update={"manifest": run_manifest(run)}).model_dump())
    assert run_manifest(run) == run.manifest
    assert "prompt" not in run.manifest.model_dump()
    with pytest.raises(ValueError, match="IMMUTABLE"):
        validate(run.model_copy(update={"manifest": None}), run, run.tenant_id)
    forged = run.manifest.model_copy(update={"config_version": run.config_version+1})
    with pytest.raises(ValueError, match="LINEAGE"):
        AgentRun.model_validate(run.model_copy(update={"manifest": forged}).model_dump())


def test_harness_uses_canonical_scope_policy_capability_and_approval():
    from dataclasses import replace

    from src.ai.execution.harness import harness_gate
    from src.ai.execution.models import HarnessIntent
    from src.ai.workflow.models import AgentRun
    from src.ai.workflow.policy import run_manifest
    from src.application.security.principal import Principal
    from tests.test_multi_agent import NOW, capability, workflow
    state = workflow()
    run = AgentRun(agent_run_id=state.agent_run_id, tenant_id=state.tenant_id,
        incident_id=state.incident_id, workflow_id=state.workflow_id, job_id="job-a",
        correlation_id="correlation-a", config_version=1, jev_decision_id="d", started_at=NOW, state=state)
    run = run.model_copy(update={"manifest": run_manifest(run)})
    incident = SimpleNamespace(id=state.incident_id, tenant_id=state.tenant_id, store="store-a")
    principal = Principal("operator", state.tenant_id, frozenset({"OPS_MANAGER"}))
    config = RuntimeConfig(auto_investigation=True, multi_agent_enabled=True, allowed_tools=("voc.search",))
    intent = HarnessIntent(agent_run_id=run.agent_run_id, operation="HISTORY_LOOKUP",
        context_digest=state.contexts[0].digest)
    args = {"run": run, "incident": incident, "principal": principal, "config": config,
        "now": NOW, "capabilities": (capability(),)}
    assert harness_gate(intent, **args).allowed
    assert harness_gate(intent, **(args | {"capabilities": ()})).reason == "CAPABILITY_UNAVAILABLE"
    assert harness_gate(intent, **(args | {"principal": replace(principal, tenant_id="other")})).reason == "AUTHORIZATION_DENIED"
    assert harness_gate(intent, **(args | {"control": "STOPPED"})).reason == "STOPPED"
    assert harness_gate(intent, **(args | {"config": replace(config, allowed_tools=())})).reason == "POLICY_DENIED"
    execution = intent.model_copy(update={"operation": "INTERNAL_EXECUTION"})
    assert harness_gate(execution, **args).reason == "APPROVAL_REQUIRED"
    with pytest.raises(ValidationError):
        HarnessIntent.model_validate(intent.model_dump() | {"risk_hint": "LOW", "tenant_id": "other"})


def loop_setup(max_operations=20):
    from dataclasses import replace

    from src.ai.workflow.models import LoopTrace
    from tests.test_multi_agent import NOW, multi_setup
    p, service, source, job = multi_setup(all_agents=True)
    with p.transaction("t") as uow:
        old = uow.configs.current()
        uow.configs.append(replace(old, config_version=old.config_version+1, parent_version=old.config_version,
            config=replace(old.config, loop_enabled=True, max_tool_calls=max_operations)), old.config_version)
    # Prepare the existing explicitly authorized v5 job; pin the loop snapshot independently.
    run = service.prepare(job)[0]
    loop = LoopTrace(policy=loop_policy(replace(old.config, loop_enabled=True, max_tool_calls=max_operations)))
    with p.transaction("t") as uow:
        run = uow.agent_runs.save(run.model_copy(update={"state": run.state.model_copy(update={"loop": loop})}))
    return p, source, run, NOW


def test_bounded_retry_and_no_new_evidence_preserves_append_only_results():
    from uuid import NAMESPACE_URL, uuid5

    from src.ai.workflow.agents import branch_gap
    from src.ai.workflow.controller import InvestigationLoop
    p, source, run, now = loop_setup()
    pack = run.state.contexts[0]
    bid = str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+pack.agent_type))
    calls = []
    def unavailable(context, branch_id):
        calls.append(branch_id)
        return branch_gap(context, branch_id, lambda: now, code="SOURCE_UNAVAILABLE", status="UNAVAILABLE", retryable=True)
    controller = InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now)
    first = controller.execute(pack, bid, unavailable)
    assert len(calls) == 2 and first.status == "UNAVAILABLE"
    assert controller.execute(pack, bid, unavailable) == first and len(calls) == 2
    with p.transaction("t") as uow:
        saved = uow.agent_runs.get(run.agent_run_id)
        assert saved.state.loop.termination == "NO_NEW_EVIDENCE"
        assert saved.state.iteration == 2 and saved.state.tool_call_count == 2
        assert len(uow.agent_runs.events(run.agent_run_id)) == 4


def test_operation_budget_and_uncertain_claim_are_fail_closed():
    from uuid import NAMESPACE_URL, uuid5

    from src.ai.workflow.agents import branch_gap
    from src.ai.workflow.controller import ControlInterrupted, InvestigationLoop
    from src.ai.workflow.models import RuntimeEvent
    p, source, run, now = loop_setup(1)
    controller = InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now)
    first, second = run.state.contexts[:2]
    calls = []
    def action(pack, bid):
        calls.append(bid)
        return branch_gap(pack, bid, lambda: now, code="NO_EVIDENCE_FOUND", status="NO_EVIDENCE")
    for pack in (first, second):
        controller.execute(pack, str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+pack.agent_type)), action)
    assert len(calls) == 1
    with p.transaction("t") as uow:
        assert uow.agent_runs.get(run.agent_run_id).state.loop.termination == "BUDGET_EXHAUSTED"
    p, source, run, now = loop_setup()
    pack = run.state.contexts[0]
    with p.transaction("t") as uow:
        uow.agent_runs.append_event(run.agent_run_id, RuntimeEvent(event_id="uncertain", kind="CLAIM",
            agent_type=pack.agent_type, created_at=now))
    with pytest.raises(ControlInterrupted, match="INCOMPLETE"):
        InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now).execute(pack,
            str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+pack.agent_type)), action)
    assert len(calls) == 1
