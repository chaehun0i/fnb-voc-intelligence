"""Explicit isolated synthetic task fixture; never automatically seeds an operating tenant."""
import os
from dataclasses import replace
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from scripts.serviq_ax_rc_smoke import EmptyHistory
from scripts.serviq_multi_agent_smoke import CountHistory, seed

from src.ai.ax.validation import validate_synthetic_database_name
from src.ai.execution.models import InternalReviewSimulation
from src.ai.execution.service import VerificationCommands
from src.ai.workflow.runtime import HistoryProcessor, postgres_checkpoint
from src.application.agent_controls import AgentControls
from src.application.data_intake import DataIntake
from src.application.security.principal import RequestContext, Role
from src.application.user_validation import UserValidation, ValidationSignal
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor

SCENARIOS = ("happy_path", "more_evidence", "reopen", "manual_takeover", "abandon")


def require_isolated_database(dsn):
    name = conninfo_to_dict(dsn).get("dbname", "")
    validate_synthetic_database_name(name)


def prepare_synthetic(dsn, scenario):
    require_isolated_database(dsn)
    if scenario not in SCENARIOS:
        raise ValueError("UNKNOWN_VALIDATION_SCENARIO")
    p, source, principal, job, incident = seed(dsn, tenant="validation-synthetic-"+uuid4().hex,
        loop=True, closed_loop=True, sample_dataset=True)
    context = RequestContext(principal, "synthetic-validation", job.correlation_id, "session")
    svc = UserValidation(p, context)
    session = svc.start(incident.store, scenario, consent=True, kind="SYNTHETIC")
    intake = DataIntake(p, replace(context, idempotency_key="sample"))
    receipt = intake.sample(incident.store)
    assert receipt["sample"] and intake.sample(incident.store) == receipt
    search = EmptyHistory(dsn) if scenario == "more_evidence" else CountHistory(dsn)
    processor = HistoryProcessor(p, search, lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
    for milestone in ("ONBOARDING_STARTED", "DATA_READY", "INCIDENT_OPENED"):
        UserValidation(p, replace(context, idempotency_key=milestone)).signal(session.session_id,
            ValidationSignal(surface="INCIDENT", milestone=milestone, incident_id=incident.id))
    return p, processor, principal, job, incident, session


def run_scenario(dsn, scenario):
    p, processor, principal, job, incident, session = prepare_synthetic(dsn, scenario)
    context = RequestContext(principal, "synthetic", job.correlation_id, "task")
    if scenario == "abandon":
        svc = UserValidation(p, context)
        event = svc.signal(session.session_id, ValidationSignal(surface="INCIDENT", friction="TASK_ABANDONED"))
        assert svc.signal(session.session_id, ValidationSignal(surface="INCIDENT", friction="TASK_ABANDONED")) == event
        assert svc.get(session.session_id)["session"].status == "ABANDONED"
        print("[PASS] Synthetic scenario abandon · 실제 사용자 검증 아님 · external write 0")
        return p, context, incident, session
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
        assert worker.run_once() and worker.run_once()
    with p.transaction(principal.tenant_id) as uow:
        run = uow.agent_runs.by_job(job.job_id)
    for milestone in ("AI_BRIEF_VIEWED", "HUMAN_ACTION_PRESENTED"):
        UserValidation(p, replace(context, idempotency_key=milestone)).signal(session.session_id,
            ValidationSignal(surface="INCIDENT", milestone=milestone))
    if scenario == "manual_takeover":
        AgentControls(p).execute(context, incident.id, run.agent_run_id, "takeover", 0)
    elif scenario in {"happy_path", "reopen"}:
        for milestone in ("EVIDENCE_REVIEWED", "REVIEW_OPENED"):
            UserValidation(p, replace(context, idempotency_key=milestone)).signal(session.session_id,
                ValidationSignal(surface="REVIEW", milestone=milestone))
        from fastapi.testclient import TestClient

        from src.api.app import create_app
        from src.infrastructure.auth.local_identity_provider import (
            LocalIdentityProvider,
        )
        reviewer = replace(principal, principal_id="synthetic-reviewer", roles=frozenset({Role.REVIEWER}))
        app = create_app(p.incidents, identity_provider=LocalIdentityProvider({"human": reviewer}, environment="test"))
        app.state.access_persistence = p
        VerificationCommands(p, run.agent_run_id, principal.tenant_id).prepare_simulation(context,
            InternalReviewSimulation(tenant_id=principal.tenant_id, store=incident.store,
                agent_run_id=run.agent_run_id, source_ref="internal-review:"+str(uuid4()),
                review_record_present=scenario == "happy_path", additional_evidence_refs=run.state.evidence_refs))
        response = TestClient(app).post(f"/api/v1/reviews/{run.state.approval.approval_id}/approve",
            headers={"Authorization": "Bearer human", "Idempotency-Key": "decision"},
            json={"reason": "합성 검증", "expected_version": 1})
        assert response.status_code == 200, response.text
        with psycopg.connect(dsn, autocommit=True) as connection:
            worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
            assert worker.run_once() and not worker.run_once()
        current = p.incidents.get(incident.id, tenant_id=principal.tenant_id)
        assert current.status.value == ("RESOLVED" if scenario == "happy_path" else "REOPENED")
        for milestone in ("DECISION_SUBMITTED", "VERIFICATION_VIEWED", "FINAL_STATUS_VIEWED"):
            UserValidation(p, replace(context, idempotency_key=milestone)).signal(session.session_id,
                ValidationSignal(surface="VERIFICATION", milestone=milestone))
    decision = {"more_evidence": "REQUEST_MORE_EVIDENCE", "manual_takeover": "MANUAL_TAKEOVER"}.get(scenario, "ACCEPT")
    svc = UserValidation(p, replace(context, idempotency_key="feedback"))
    body = ValidationSignal(surface="INCIDENT", feedback_decision=decision)
    event = svc.signal(session.session_id, body)
    assert event == svc.signal(session.session_id, body)
    assert event.feedback_stage == "RAW" and event.source_run_id == run.agent_run_id and event.run_manifest_ref
    assert svc.get(session.session_id)["journey"].task_success
    finished = UserValidation(p, replace(context, idempotency_key="complete")).finish(session.session_id)
    assert finished.status == "COMPLETED"
    print("[PASS] Synthetic scenario "+scenario+" · 실제 사용자 검증 아님 · external write 0")
    return p, context, incident, session


def main():
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("격리된 SERVIQ_TEST_DATABASE_URL을 지정해 주세요.")
    for scenario in SCENARIOS:
        run_scenario(dsn, scenario)


if __name__ == "__main__":
    main()
