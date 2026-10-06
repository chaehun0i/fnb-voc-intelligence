from dataclasses import replace

import pytest

from src.agents.capa_commands import CAPACommands
from src.application.security.principal import AccessError
from src.domain.approvals.models import action_digest
from tests.test_capa_application import prepared


def test_real_approval_digest_and_duplicate_request():
    p, run, state, _, _ = prepared()
    cmd = CAPACommands(p, run.agent_run_id, "t")
    applied = cmd.apply(state)
    waiting = cmd.request_approval(applied)
    assert cmd.request_approval(applied) == waiting
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        approval = uow.approvals.get(waiting.approval.approval_id)
        assert incident.status == "PENDING_APPROVAL" and approval.agent_run_id == run.agent_run_id
        assert approval.action_digest == action_digest(incident) and len(uow.approvals.list()) == 1
        changed = replace(incident, corrective_actions=[replace(incident.corrective_actions[0], target_reference="other")])
        assert action_digest(changed) != approval.action_digest


def test_unsupported_critical_two_person_policy_does_not_downgrade():
    p, run, state, _, _ = prepared()
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        uow.incidents.save(replace(incident, severity="CRITICAL"))
        run = uow.agent_runs.get(run.agent_run_id).model_copy(update={"initial_incident_version": incident.version+1})
        p.memory.data["agent_runs"][run.agent_run_id] = run
    cmd = CAPACommands(p, run.agent_run_id, "t")
    applied = cmd.apply(state)
    with pytest.raises(AccessError, match="APPROVAL_POLICY_UNSUPPORTED"):
        cmd.request_approval(applied)
    with p.transaction("t") as uow:
        assert not uow.approvals.list()
