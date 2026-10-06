from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.application.commands.incidents import IncidentCommands
from src.application.incidents.service import IncidentService
from src.application.ports.incident_repository import IncidentConflict
from src.application.security.principal import (
    AccessError,
    Principal,
    RequestContext,
    Role,
)
from src.application.workflows.resume import RESUME_JOB
from src.runtime.workflows.checkpoint import memory_checkpoint
from src.runtime.workflows.processor import HistoryProcessor
from tests.test_capa_application import prepared


def waiting_run():
    p, run, state, job, _ = prepared()
    with p.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"iteration": 1, "rca_completed": True})}))
    saver = memory_checkpoint()
    @contextmanager
    def factory():
        yield saver
    processor = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    return p, processor(job), factory


def commands(p, run, actor="reviewer", role=Role.REVIEWER, key="decision"):
    return IncidentCommands(IncidentService(p.incidents, clock=lambda: run.started_at), p,
        RequestContext(Principal(actor, "t", frozenset({role})), "request", "correlation", key))


@pytest.mark.parametrize("decision,phase", [("approve", "READY_TO_EXECUTE"), ("reject", "REJECTED")])
def test_human_decision_restart_resume_and_idempotent_replay(decision, phase):
    p, run, factory = waiting_run()
    aid = run.state.approval.approval_id
    command = getattr(commands(p, run), "review_"+decision)
    result = command(aid, "확인했습니다", 1)
    assert command(aid, "확인했습니다", 1) == result
    with p.transaction("t") as uow:
        jobs = uow.jobs.list(job_type=RESUME_JOB)
        assert len(jobs) == 1
    # 프로세서 객체를 교체해 checkpoint에서 실제 Command(resume)를 수행합니다.
    processor = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    completed = processor(jobs[0])
    assert completed.status == "COMPLETED" and completed.state.approval.phase == phase
    assert processor(jobs[0]) == completed
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        assert all(a.status != "EXECUTED" for a in incident.corrective_actions)
        assert incident.status == ("PENDING_APPROVAL" if decision == "approve" else "ACTION_PROPOSED")
        assert len(uow.approvals.list()) == 1


def test_stale_and_requester_approval_are_denied_before_decision():
    p, run, _ = waiting_run()
    aid = run.state.approval.approval_id
    with pytest.raises(AccessError):
        commands(p, run, actor="operator", role=Role.HQ_ADMIN).review_approve(aid, "사유", 1)
    with p.transaction("t") as uow:
        incident = uow.incidents.get("i")
        uow.incidents.save(replace(incident, owner="changed"))
    with pytest.raises(IncidentConflict):
        commands(p, run).review_approve(aid, "사유", 1)
    with p.transaction("t") as uow:
        assert uow.approvals.get(aid).status == "PENDING" and not uow.jobs.list(job_type=RESUME_JOB)
