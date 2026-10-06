from dataclasses import replace

import pytest

from src.ai.execution.service import VerificationCommands
from src.ai.workflow.runtime import CAPACommands
from src.application.ports.incident_repository import IncidentConflict
from src.application.security.principal import AccessError
from tests.test_approval_resume import commands
from tests.test_capa_application import prepared


def approved_run():
    p, run, state, _, _ = prepared(internal_execution=True)
    capa = CAPACommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    state = capa.request_approval(capa.apply(state))
    with p.transaction("t") as uow:
        run = uow.agent_runs.get(run.agent_run_id)
    commands(p, run).review_approve(run.state.approval.approval_id, "검토 완료", 1)
    state = CAPACommands(p, run.agent_run_id, "t", clock=lambda: run.started_at).approval_result(run.state)
    return p, run, state, None


def test_internal_execution_is_atomic_and_replayed():
    p, run, state, _ = approved_run()
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    result = c.execute(state)
    assert result.execution.execution_mode == "INTERNAL_RECORD_ONLY"
    assert c.execute(state) == result
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        assert incident.status == "EXECUTING" and incident.corrective_actions[0].status == "APPROVED"
        assert uow.executions.get(run.agent_run_id) == result.execution


def test_execution_rechecks_digest_and_tenant():
    p, run, state, _ = approved_run()
    with pytest.raises(AccessError):
        VerificationCommands(p, run.agent_run_id, "other").execute(state)
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        uow.incidents.save(replace(incident, owner="changed"))
    with pytest.raises(IncidentConflict):
        VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at).execute(state)


def test_verifying_requires_valid_execution_and_replays_without_new_version():
    p, run, state, _ = approved_run()
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    with pytest.raises(IncidentConflict):
        c.begin_verification(state)
    executing = c.execute(state)
    result = c.begin_verification(executing)
    assert result.resulting_incident_status == "VERIFYING"
    assert c.begin_verification(executing) == result
    assert p.incidents.get("i").version == executing.execution.incident_version+1
