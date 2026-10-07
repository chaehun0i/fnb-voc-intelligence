"""AX assertions over existing safety boundaries, not a parallel workflow fixture/runtime."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.ai.ax.measurement import metrics
from src.ai.ax.releases import BLOCKERS, GoldenCaseResult, GoldenComparison
from src.ai.ax.service import IncidentAXQueries
from src.ai.execution.runtime import ToolHarness
from src.ai.execution.tools import ToolFailure
from src.application.agent_controls import AgentControls
from tests.test_loop_harness import control_context, loop_setup


@pytest.mark.parametrize("action,status", [("pause", "PAUSED"), ("stop", "STOPPED"), ("takeover", "MANUAL_TAKEOVER")])
def test_ax_control_golden_preserves_evidence_and_fences_new_tools(action, status):
    p, source, run, now = loop_setup()
    harness = ToolHarness(p, source, tenant_id=run.tenant_id, run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    harness.execute("get_transactions", {"incident_id": run.incident_id})
    before = IncidentAXQueries(p, control_context()).get(run.incident_id)
    commands = AgentControls(p, lambda: now)
    commands.execute(control_context(), run.incident_id, run.agent_run_id, action, 0)
    view = IncidentAXQueries(p, control_context()).get(run.incident_id)
    assert view.runtime.control_status == status and view.coverage == before.coverage
    assert view.manifest_reference == before.manifest_reference
    with pytest.raises(ToolFailure):
        harness.execute("get_transactions", {"incident_id": run.incident_id})
    if action == "pause":
        commands.execute(control_context(key="resume"), run.incident_id, run.agent_run_id, "resume", 1)
        assert IncidentAXQueries(p, control_context()).get(run.incident_id).runtime.control_status == "RUNNING"
    else:
        assert not view.runtime.permissions["resume"] and view.next_action.action_type == "MANUAL_REVIEW"
    assert next(m for m in view.metrics if m.name == "human_intervention").value == 1


def test_unknown_effect_ax_prohibits_retry_and_preserves_uncertain_receipt():
    import asyncio

    from src.mcp.server import call_in_memory
    p, source, run, now = loop_setup()
    source.observations = Mock(side_effect=LookupError("credential=SECRET"))
    harness = ToolHarness(p, source, tenant_id=run.tenant_id, run_id=run.agent_run_id,
        agent_type="TRANSACTION", clock=lambda: now)
    for _ in range(2):
        with pytest.raises(ToolFailure) as error:
            asyncio.run(call_in_memory(harness, "get_transactions", {"incident_id": run.incident_id}))
        assert error.value.error.code == "OUTCOME_UNKNOWN" and not error.value.error.retryable
    view = IncidentAXQueries(p, control_context()).get(run.incident_id)
    assert source.observations.call_count == 1
    assert view.next_action.action_type == "MANUAL_REVIEW" and "다시 실행하지 말고" in view.next_action.reason
    assert "SECRET" not in view.model_dump_json() and view.human_action == "MANUAL_TAKEOVER_RECOMMENDED"


@pytest.mark.parametrize("blocker", BLOCKERS)
def test_each_critical_blocker_prevents_rc_pass(blocker):
    case = GoldenCaseResult(case_id="critical", safety_passed=True, completion_passed=True,
        ax_passed=True, blockers=(blocker,))
    comparison = GoldenComparison(baseline_reference="day29", candidate_id="rc", cases=(case,), required_cases=("critical",))
    assert not comparison.passed


def test_metrics_use_actual_step_and_approval_times_without_inferred_latency():
    from datetime import timedelta
    from types import SimpleNamespace
    p, _, run, now = loop_setup()
    with p.transaction(run.tenant_id) as uow:
        incident = replace(uow.incidents.get(run.incident_id), created_at=now.isoformat())
    step = SimpleNamespace(evidence_refs=("review:one",), completed_at=now+timedelta(seconds=5))
    approval = SimpleNamespace(decided_at=(now+timedelta(seconds=20)).isoformat())
    values = {m.name: m for m in metrics(incident, run, (step,), approval=approval)}
    assert values["time_to_first_useful_evidence"].value == 5
    assert values["time_to_decision"].value == 20
    assert values["cost_per_completed_incident"].status == "UNAVAILABLE"
    assert values["human_intervention"].status == "PARTIAL"
