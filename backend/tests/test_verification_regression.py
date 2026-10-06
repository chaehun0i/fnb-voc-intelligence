from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from src.ai.execution.models import InternalReviewSimulation
from src.ai.execution.service import VerificationCommands
from src.ai.workflow.models import WorkflowState
from src.ai.workflow.runtime import RESUME_JOB, HistoryProcessor, SafeJsonSerializer
from src.application.ports.incident_repository import IncidentConflict
from src.application.security.principal import (
    AccessError,
    Principal,
    RequestContext,
    Role,
)
from src.infrastructure.jobs.job_worker import RetryableJobError
from tests.test_approval_resume import commands
from tests.test_capa_application import prepared
from tests.test_internal_execution import approved_run
from tests.test_verification_node import post_evidence, verifying_state


@pytest.mark.parametrize("mutation", ["digest", "policy", "expiry", "approval"])
def test_execution_fails_closed_and_never_records_stale_approval(mutation):
    p, run, state, _ = approved_run()
    with p.transaction("t") as uow:
        if mutation == "digest":
            incident = uow.incidents.get("i")
            uow.incidents.save(replace(incident, corrective_actions=[replace(incident.corrective_actions[0], verification_criteria="changed")]))
        elif mutation == "policy":
            current = uow.configs.current()
            uow.configs.append(replace(current, config_version=3, parent_version=2, config=replace(current.config, internal_execution_enabled=False)), 2)
        elif mutation == "approval":
            approval = uow.approvals.get(state.approval.approval_id)
            # 승인 저장소 자체도 결정 후 UPDATE를 거부합니다. 손상된 복원
            # source를 주입해 execution 경계가 그 값도 신뢰하지 않는지 검사합니다.
            with pytest.raises(IncidentConflict):
                uow.approvals.save(replace(approval, status="REJECTED"))
            p.memory.data["approvals"][approval.approval_id] = replace(approval, status="REJECTED")
    clock = lambda: run.started_at+timedelta(days=2) if mutation == "expiry" else run.started_at
    with pytest.raises((IncidentConflict, AccessError)):
        VerificationCommands(p, run.agent_run_id, "t", clock=clock).execute(state)
    with p.transaction("t") as uow:
        assert uow.executions.get(run.agent_run_id) is None
        assert uow.incidents.get("i").status == "PENDING_APPROVAL"


def test_execution_audit_failure_rolls_back_all_business_effects(monkeypatch):
    p, run, state, _ = approved_run()
    before = p.incidents.get("i")
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    def fail(*_):
        raise RuntimeError("audit failure")
    monkeypatch.setattr(c, "audit", fail)
    with pytest.raises(RuntimeError):
        c.execute(state)
    assert p.incidents.get("i") == before
    with p.transaction("t") as uow:
        assert uow.executions.get(run.agent_run_id) is None


@pytest.mark.parametrize("kind", ["tenant", "store", "role", "reference"])
def test_post_action_source_rejects_unauthorized_or_fabricated_input(kind):
    p, run, state = verifying_state()
    principal = Principal("reader", "other" if kind == "tenant" else "t",
        frozenset({Role.AUDITOR if kind == "role" else Role.HQ_ADMIN}),
        frozenset({"elsewhere"}) if kind == "store" else frozenset())
    source = post_evidence(state, True)
    if kind == "reference":
        source = source.model_copy(update={"additional_evidence_refs": ("review:fabricated",)})
    with pytest.raises((AccessError, IncidentConflict)):
        VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at).record_evidence(
            RequestContext(principal, "r", "c"), source, p.incidents.get("i").version)


def test_fabricated_pass_candidate_and_missing_evidence_cannot_resolve():
    p, run, state = verifying_state()
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    candidate = c.evaluate(state)
    assert candidate.verification.result == "INCONCLUSIVE"
    fabricated = candidate.model_copy(update={"verification": candidate.verification.model_copy(update={"result": "PASS", "evidence_ids": ("fake",)})})
    with pytest.raises(IncidentConflict):
        c.apply(fabricated)
    assert p.incidents.get("i").status == "VERIFYING"


def test_old_pass_candidate_is_rechecked_after_checkpoint_delay():
    p, run, state = verifying_state()
    now = [run.started_at]
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: now[0])
    context = RequestContext(Principal("operator", "t", frozenset({Role.HQ_ADMIN})), "r", "c")
    c.record_evidence(context, post_evidence(state, True), p.incidents.get("i").version)
    candidate = c.evaluate(state)
    assert candidate.verification.result == "PASS"
    now[0] += timedelta(days=2)
    applied = c.apply(candidate)
    assert applied.verification.result == "INCONCLUSIVE"
    assert applied.verification.reason_codes == ("EVIDENCE_STALE",)
    assert p.incidents.get("i").status == "VERIFYING"
    assert c.apply(applied) == applied


@pytest.mark.parametrize("change", [{"tenant_id": "other"}, {"store": "elsewhere"},
    {"agent_run_id": "other"}, {"action_id": "other"}, {"additional_evidence_refs": ("review:fake",)}])
def test_restored_state_rejects_foreign_verification_source(change):
    _, _, state = verifying_state()
    evidence = post_evidence(state, True).model_copy(update=change)
    with pytest.raises(ValidationError):
        WorkflowState.model_validate(state.model_copy(update={"verification_evidence": (evidence,)}).model_dump(mode="json"))


class FailExecutionCheckpoint(InMemorySaver):
    def __init__(self, target):
        super().__init__(serde=SafeJsonSerializer())
        self.target, self.failed = target, False

    def put(self, config, checkpoint, metadata, new_versions):
        snapshot = checkpoint.get("channel_values", {}).get("snapshot", {})
        if not self.failed and snapshot.get(self.target):
            self.failed = True
            raise psycopg.OperationalError("verification checkpoint fault")
        return super().put(config, checkpoint, metadata, new_versions)


@pytest.mark.parametrize("target", ["execution", "verification"])
def test_checkpoint_failure_after_business_commit_resumes_without_duplicate_effect(target):
    p, run, state, job, _ = prepared(internal_execution=True)
    with p.transaction("t") as uow:
        uow.agent_runs.save(run.model_copy(update={"state": state.model_copy(update={"iteration": 1, "rca_completed": True})}))
    saver = FailExecutionCheckpoint(target)
    @contextmanager
    def factory():
        yield saver
    processor = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)
    waiting = processor(job)
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    context = RequestContext(Principal("operator", "t", frozenset({Role.HQ_ADMIN})), "r", "c")
    c.prepare_simulation(context, InternalReviewSimulation(tenant_id="t", store="store", agent_run_id=run.agent_run_id,
        source_ref="internal-review:11111111-1111-1111-1111-111111111111", review_record_present=True, additional_evidence_refs=waiting.state.evidence_refs))
    commands(p, waiting).review_approve(waiting.state.approval.approval_id, "검토", 1)
    with p.transaction("t") as uow:
        resume = uow.jobs.list(job_type=RESUME_JOB)[0]
    with pytest.raises(RetryableJobError):
        processor(resume)
    assert p.incidents.get("i").status != "FAILED"
    restored = HistoryProcessor(p, Mock(), factory, clock=lambda: run.started_at)(resume)
    assert restored.status == "COMPLETED" and p.incidents.get("i").status == "RESOLVED"
    assert processor(resume) == restored
    with p.transaction("t") as uow:
        assert len(uow.executions.evidence(restored.state.execution)) == 1
        assert len(uow.approvals.list("i")) == 1
        assert len(uow.agent_runs.history("i")) == 1
