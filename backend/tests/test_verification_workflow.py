from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.application.security.principal import Principal, RequestContext, Role
from src.application.workflows.resume import RESUME_JOB
from src.application.workflows.verification import VerificationCommands
from src.domain.workflows.verification import InternalReviewSimulation
from src.infrastructure.workflows.checkpoint import memory_checkpoint
from src.infrastructure.workflows.processor import HistoryProcessor
from tests.test_approval_resume import commands
from tests.test_capa_application import prepared


@pytest.mark.parametrize("present,final", [(True, "RESOLVED"), (False, "REOPENED"), (None, "VERIFYING")])
def test_golden_closed_loop_checkpoint_resume(present, final):
    p, run, state, job, _ = prepared(internal_execution=True)
    with p.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"iteration": 1, "rca_completed": True})}))
    saver = memory_checkpoint()
    @contextmanager
    def factory():
        yield saver
    processor = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    waiting = processor(job)
    assert waiting.status == "WAITING_APPROVAL"
    context = RequestContext(Principal("operator", "t", frozenset({Role.HQ_ADMIN})), "r", "c")
    VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at).prepare_simulation(context,
        InternalReviewSimulation(tenant_id="t", store="store", agent_run_id=run.agent_run_id,
            source_ref="internal-review:"+str(uuid4()), review_record_present=present,
            additional_evidence_refs=waiting.state.evidence_refs))
    commands(p, waiting).review_approve(waiting.state.approval.approval_id, "합성 검토 승인", 1)
    with p.transaction("t") as uow:
        resume = uow.jobs.list(job_type=RESUME_JOB)[0]
    restarted = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    completed = restarted(resume)
    assert completed.status == "COMPLETED" and completed.state.resulting_incident_status == final
    assert p.incidents.get("i").status == final
    assert completed.state.execution.execution_mode == "INTERNAL_RECORD_ONLY"
    assert completed.state.verification.observation_mode == "SIMULATED"
    assert restarted(resume) == completed
    with p.transaction("t") as uow:
        assert len(uow.executions.evidence(completed.state.execution)) == 1
        assert {s.node_name for s in uow.agent_runs.steps(run.agent_run_id)} >= {"internal_execution", "verification", "apply_verification"}
