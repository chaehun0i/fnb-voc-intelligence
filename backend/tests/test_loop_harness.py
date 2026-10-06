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


def test_rca_preserves_investigation_iteration_and_obeys_lower_current_budget():
    from dataclasses import replace

    from src.ai.workflow.models import LoopTrace
    from src.ai.workflow.policy import bounded_loop_config
    from src.domain.config.resolution import ConfigResolver
    from tests.test_rca_investigation import node, ready

    policy = loop_policy(RuntimeConfig())
    initial = ready().model_copy(update={"iteration": 3, "loop": LoopTrace(policy=policy)})
    result = node()(initial)
    assert result.rca_candidates and result.iteration == 3
    pinned = ConfigResolver().resolve(RuntimeConfig(token_budget=4000))
    bounded = bounded_loop_config(pinned, replace(pinned.effective, token_budget=500,
        cost_budget_usd=.1, timeout_seconds=10), policy)
    assert bounded.effective.token_budget == 500
    assert bounded.effective.cost_budget_usd == .1 and bounded.effective.timeout_seconds == 10
    assert bounded.sources == pinned.sources
    assert pinned.effective.token_budget == 4000


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
        # Branch exhaustion is sticky; the global termination is decided only after all branches fan in.
        assert saved.state.loop.termination is None
        assert saved.state.iteration == 2 and saved.state.tool_call_count == 2
        assert len([e for e in uow.agent_runs.events(run.agent_run_id) if e.kind in {"CLAIM", "RESULT"}]) == 4


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


def test_manifest_compatibility_rejects_changed_bundle():
    from src.ai.workflow.policy import validate_manifest
    _, _, run, _ = loop_setup()
    validate_manifest(run)
    manifest = run.manifest.model_copy(update={"source_digest": "0"*64})
    with pytest.raises(ValueError, match="MANIFEST_INCOMPATIBLE"):
        validate_manifest(run.model_copy(update={"manifest": manifest}))


def control_context(key="control-1", tenant="t", role="OPS_MANAGER", stores=()):
    from src.application.security.principal import Principal, RequestContext
    return RequestContext(Principal("operator", tenant, frozenset({role}), frozenset(stores)),
        "control-request", "control-correlation", key)


def test_pause_resume_stop_are_idempotent_and_queued_work_is_fenced():
    from src.ai.workflow.controller import (
        ControlInterrupted,
        InvestigationLoop,
        control_state,
    )
    from src.application.agent_controls import CONTINUE_JOB, AgentControls
    from src.application.security.principal import AccessError
    p, source, run, now = loop_setup()
    commands = AgentControls(p, lambda: now)
    pause = commands.execute(control_context(), "i", run.agent_run_id, "pause", 0)
    assert commands.execute(control_context(), "i", run.agent_run_id, "pause", 0) == pause
    with pytest.raises(ControlInterrupted, match="PAUSED"):
        InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now).authorize()
    commands.execute(control_context("resume"), "i", run.agent_run_id, "resume", 1)
    InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now).authorize()
    with p.transaction("t") as uow:
        jobs = uow.jobs.list(job_type=CONTINUE_JOB)
        assert len(jobs) == 1 and jobs[0].parent_job_id == run.job_id
        assert control_state(uow.agent_runs.events(run.agent_run_id)) == "RUNNING"
    commands.execute(control_context("stop"), "i", run.agent_run_id, "stop", 2)
    with pytest.raises(ControlInterrupted, match="STOPPED"):
        InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now).authorize()
    with pytest.raises(AccessError, match="AGENT_CONTROL_NOT_ALLOWED"):
        commands.execute(control_context("retry"), "i", run.agent_run_id, "resume", 3)
    with p.transaction("t") as uow:
        assert uow.agent_runs.get(run.agent_run_id).manifest == run.manifest
        assert uow.agent_runs.automation_blocked("i")
        assert len(uow.audit.list()) >= 3


def test_takeover_and_security_and_control_version_fail_closed():
    from src.ai.workflow.controller import ControlInterrupted, InvestigationLoop
    from src.application.agent_controls import AgentControls
    from src.application.incidents.service import IncidentNotFound
    from src.application.security.principal import AccessError
    p, source, run, now = loop_setup()
    commands = AgentControls(p, lambda: now)
    with pytest.raises(IncidentNotFound):
        commands.execute(control_context(tenant="other"), "i", run.agent_run_id, "pause", 0)
    with pytest.raises(AccessError):
        commands.execute(control_context(role="STORE_MANAGER", stores=("wrong",)), "i", run.agent_run_id, "pause", 0)
    with pytest.raises(AccessError, match="AGENT_CONTROL_CONFLICT"):
        commands.execute(control_context(), "i", run.agent_run_id, "pause", 10)
    commands.execute(control_context(), "i", run.agent_run_id, "takeover", 0)
    with pytest.raises(ControlInterrupted, match="MANUAL_TAKEOVER"):
        InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now).authorize()
    with pytest.raises(AccessError, match="IDEMPOTENCY_CONFLICT"):
        commands.execute(control_context(), "i", run.agent_run_id, "takeover", 1)


def test_control_http_and_safe_ax_projection():
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
    p, _, run, _ = loop_setup()
    identities = LocalIdentityProvider({"operator": control_context().principal,
        "other": control_context(tenant="other").principal,
        "store": control_context(role="STORE_MANAGER", stores=("wrong",)).principal,
        "reader": control_context(role="AUDITOR").principal}, environment="test")
    app = create_app(p.incidents, identity_provider=identities)
    app.state.access_persistence = p
    client = TestClient(app)
    path = "/api/v1/incidents/i/agent-runs/"+run.agent_run_id
    header = {"Authorization": "Bearer operator", "Idempotency-Key": "pause"}
    detail = client.get(path, headers=header)
    assert detail.status_code == 200
    assert detail.json()["runtime"]["permissions"]["pause"]
    assert not client.get(path, headers={"Authorization": "Bearer reader"}).json()["runtime"]["permissions"]["pause"]
    for token, code in (("other", 404), ("store", 403), ("reader", 403)):
        assert client.post(path+"/controls/pause", headers=header | {"Authorization": "Bearer "+token},
            json={"expected_version": 0}).status_code == code
    assert client.post(path+"/controls/pause", headers=header,
        json={"expected_version": 0, "token_budget": 999999}).status_code == 422
    assert client.post(path+"/controls/pause", headers=header, json={"expected_version": 0}).json() == {"control_status": "PAUSED"}
    response = client.get(path, headers=header)
    assert response.json()["runtime"]["control_version"] == 1
    assert response.json()["runtime"]["permissions"]["resume"]
    assert not any(s in response.text for s in ("raw_prompt", "source_digest", "actor_id", "Idempotency-Key", "delegated_roles"))


def test_pinned_loop_budget_cannot_be_increased_and_completed_branch_never_retried():
    from uuid import NAMESPACE_URL, uuid5

    from src.ai.workflow.controller import InvestigationLoop
    from src.ai.workflow.models import InvestigationResult
    p, source, run, now = loop_setup()
    raised = run.state.loop.model_copy(update={"policy": run.state.loop.policy.model_copy(update={"max_operations": 50})})
    with p.transaction("t") as uow, pytest.raises(ValueError, match="LOOP_POLICY_IMMUTABLE"):
        uow.agent_runs.save(run.model_copy(update={"state": run.state.model_copy(update={"loop": raised})}))
    pack = run.state.contexts[0]
    bid = str(uuid5(NAMESPACE_URL, run.agent_run_id+":"+pack.agent_type))
    calls = []
    def success(context, identity):
        calls.append(identity)
        return InvestigationResult(agent_type=context.agent_type, branch_id=identity, tenant_id=context.tenant_id,
            incident_id=context.incident_id, store=context.store, status="SUCCESS", context_digest=context.digest,
            started_at=now, completed_at=now, uncertainty="OBSERVATIONS_NOT_CAUSE", retryable=True)
    loop = InvestigationLoop(p, run.agent_run_id, "t", source, lambda: now)
    first = loop.execute(pack, bid, success)
    assert loop.execute(pack, bid, success) == first and len(calls) == 1
