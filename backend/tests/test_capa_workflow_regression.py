from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from src.application.ports.incident_repository import IncidentConflict
from src.application.security.principal import AccessError, Role
from src.application.workflows.capa import CAPACommands
from src.application.workflows.resume import RESUME_JOB
from src.domain.workflows.models import WorkflowStatus
from src.infrastructure.queue.worker import RetryableJobError
from src.infrastructure.workflows.checkpoint import SafeJsonSerializer
from src.infrastructure.workflows.processor import HistoryProcessor
from tests.test_approval_resume import commands, waiting_run
from tests.test_capa_application import prepared


@pytest.mark.parametrize("change", [{"auto_capa_draft": False}, {"separation_of_duties": False},
    {"required_roles": ("HQ_ADMIN",)}, {"critical_approver_count": 1}])
def test_changed_approval_policy_is_stale_before_human_decision(change):
    p, run, _ = waiting_run()
    with p.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=3, parent_version=2,
            config=replace(version.config, **change)), 2)
    with pytest.raises(IncidentConflict):
        commands(p, run).review_approve(run.state.approval.approval_id, "검토", 1)
    with p.transaction("t") as uow:
        assert uow.approvals.get(run.state.approval.approval_id).status == "PENDING"
        assert not uow.jobs.list(job_type=RESUME_JOB)


def test_non_policy_config_change_preserves_pinned_run_and_valid_resume():
    p, run, factory = waiting_run()
    with p.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=3, parent_version=2,
            config=replace(version.config, token_budget=10000)), 2)
    commands(p, run).review_approve(run.state.approval.approval_id, "검토", 1)
    with p.transaction("t") as uow:
        job = uow.jobs.list(job_type=RESUME_JOB)[0]
    result = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)(job)
    assert result.config_version == 2 and result.state.approval.phase == "READY_TO_EXECUTE"


@pytest.mark.parametrize("mutation", ["digest", "incident", "policy", "expiry"])
def test_stale_after_decision_cannot_enter_approved_branch(mutation):
    p, run, factory = waiting_run()
    commands(p, run).review_approve(run.state.approval.approval_id, "검토", 1)
    with p.transaction("t") as uow:
        job = uow.jobs.list(job_type=RESUME_JOB)[0]
        incident = uow.incidents.get("i")
        if mutation == "digest":
            uow.incidents.save(replace(incident, corrective_actions=[replace(incident.corrective_actions[0], verification_criteria="changed")]))
        elif mutation == "incident":
            uow.incidents.save(replace(incident, owner="changed"))
        elif mutation == "policy":
            version = uow.configs.current()
            uow.configs.append(replace(version, config_version=3, parent_version=2,
                config=replace(version.config, auto_capa_draft=False)), 2)
    clock = (lambda: run.started_at+timedelta(days=2)) if mutation == "expiry" else lambda: run.started_at
    with pytest.raises(IncidentConflict):
        HistoryProcessor(p, Mock(), factory, clock=clock)(job)
    with p.transaction("t") as uow:
        assert uow.agent_runs.get(run.agent_run_id).state.approval.phase == "WAITING_APPROVAL"
        assert uow.incidents.get("i").status != "FAILED"


@pytest.mark.parametrize("role", [Role.AUDITOR, Role.OPS_MANAGER, Role.STORE_MANAGER])
def test_server_approval_permissions_are_not_inherited_from_requester(role):
    p, run, _ = waiting_run()
    with pytest.raises(AccessError):
        commands(p, run, role=role).review_approve(run.state.approval.approval_id, "검토", 1)


def test_idempotency_conflict_never_creates_a_second_resume():
    p, run, _ = waiting_run()
    command = commands(p, run)
    aid = run.state.approval.approval_id
    command.review_approve(aid, "검토", 1)
    with pytest.raises(AccessError, match="IDEMPOTENCY_CONFLICT"):
        command.review_approve(aid, "다른 사유", 1)
    with p.transaction("t") as uow:
        assert len(uow.jobs.list(job_type=RESUME_JOB)) == 1


class FailApprovalCheckpoint(InMemorySaver):
    def __init__(self):
        super().__init__(serde=SafeJsonSerializer())
        self.failed = False

    def put(self, config, checkpoint, metadata, new_versions):
        snapshot = checkpoint.get("channel_values", {}).get("snapshot", {})
        if not self.failed and snapshot.get("status") == "WAITING_APPROVAL":
            self.failed = True
            raise psycopg.OperationalError("approval checkpoint failure")
        return super().put(config, checkpoint, metadata, new_versions)


def test_checkpoint_failure_after_real_approval_does_not_duplicate_business_effects():
    p, run, state, job, _ = prepared()
    with p.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"iteration": 1, "rca_completed": True})}))
    saver = FailApprovalCheckpoint()
    @contextmanager
    def factory():
        yield saver
    processor = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    with pytest.raises(RetryableJobError):
        processor(job)
    with p.transaction("t") as uow:
        assert uow.agent_runs.get(run.agent_run_id).status == WorkflowStatus.FAILED
        assert len(uow.approvals.list()) == 1
        version = uow.incidents.get("i").version
    recovered = processor(job)
    assert recovered.status == WorkflowStatus.WAITING_APPROVAL
    with p.transaction("t") as uow:
        assert uow.incidents.get("i").version == version and len(uow.approvals.list()) == 1


def test_tenant_and_delegated_store_are_checked_at_capa_application():
    p, run, state, _, _ = prepared()
    with pytest.raises(AccessError):
        CAPACommands(p, run.agent_run_id, "other").apply(state)
    p.memory.data["agent_runs"][run.agent_run_id] = run.model_copy(update={"state": state,
        "delegated_store_scope": ("elsewhere",)})
    with pytest.raises(AccessError):
        CAPACommands(p, run.agent_run_id, "t").apply(state)
    assert not p.incidents.get("i").corrective_actions
