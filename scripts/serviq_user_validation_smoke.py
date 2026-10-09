"""Explicit isolated synthetic task fixture; never automatically seeds an operating tenant."""
import argparse
import json
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
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)

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
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-http", action="store_true")
    if parser.parse_args().seed_http:
        print(json.dumps(seed_http(dsn)))
        return
    for scenario in SCENARIOS:
        _, context, incident, session = run_scenario(dsn, scenario)
        verify_observation(dsn, context, incident, session)


def verify_observation(dsn, context, incident, session):
    """Fresh repository + real HTTP contracts, not an in-memory analytics substitute."""
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
    restored = AccessPersistence(PostgresIncidentRepository(dsn))
    principal = context.principal
    identities = {"owner": principal,
        "admin": replace(principal, roles=frozenset({Role.HQ_ADMIN})),
        "other": replace(principal, tenant_id="other-validation"),
        "store": replace(principal, store_scope=frozenset({"other-store"})),
        "auditor": replace(principal, roles=frozenset({Role.AUDITOR}))}
    app = create_app(restored.incidents, identity_provider=LocalIdentityProvider(identities, environment="test"))
    app.state.access_persistence = restored
    client = TestClient(app)
    path = f"/api/v1/validation/sessions/{session.session_id}"
    view = client.get(path, headers={"Authorization": "Bearer owner"})
    assert view.status_code == 200, view.text
    expected = "ABANDONED" if session.scenario_id == "abandon" else "COMPLETED"
    assert view.json()["session"]["status"] == expected
    assert view.json()["journey"]["task_success"] == (expected == "COMPLETED")
    for token, status in (("other", 404), ("store", 403)):
        assert client.get(path, headers={"Authorization": "Bearer "+token}).status_code == status
    assert client.get("/api/v1/validation/summary", params={"store": incident.store}, headers={"Authorization": "Bearer auditor"}).status_code == 403
    query = {"store": incident.store, "kind": "SYNTHETIC"}
    report = client.get("/api/v1/validation/summary", params=query, headers={"Authorization": "Bearer admin"})
    assert report.status_code == 200, report.text
    values = report.json()
    assert values["sessions"] == 1 and values["completed"] == (expected == "COMPLETED")
    assert all(m["sample_size"] <= 1 for m in values["metrics"])
    assert client.get("/api/v1/validation/summary", params=query | {"kind": "USER_OBSERVATION"}, headers={"Authorization": "Bearer admin"}).json()["sessions"] == 0
    assert not any(s in report.text for s in ("participant_ref", "principal_id", "raw_prompt", "checkpoint", "credential"))
    with restored.transaction(principal.tenant_id) as uow:
        events = uow.product_events.session_events(session.session_id)
        assert len({e.event_id for e in events}) == len(events)
        assert all(e.feedback_stage == "RAW" for e in events if e.feedback_decision)
        assert not uow.llm_calls.history(incident.id)
    print("[PASS] Session/Journey/RAW feedback/summary HTTP + PG restart/scope/dedup "+session.scenario_id)


def seed_http(dsn):
    """Only explicit isolated smoke DB; automated HTTP sessions remain SYNTHETIC."""
    require_isolated_database(dsn)
    p, source, principal, job, incident = seed(dsn, tenant="legacy-local", loop=True, closed_loop=True)
    observer = replace(principal, principal_id="local-operator", authentication_source="local-compatibility")
    context = RequestContext(observer, "synthetic-http", job.correlation_id, "session-"+job.job_id)
    session = UserValidation(p, context).start(incident.store, "happy_path", consent=True, kind="SYNTHETIC")
    processor = HistoryProcessor(p, CountHistory(dsn), lambda: postgres_checkpoint(dsn), source=source, dsn=dsn)
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, snapshot_processor(p.incidents, history=processor), tenant_id=principal.tenant_id)
        # Bounded fixture preparation; production Worker semantics are not changed.
        for _ in range(10):
            assert worker.run_once()
            with p.transaction(principal.tenant_id) as uow:
                current = uow.agent_runs.by_job(job.job_id)
            if current and current.status == "WAITING_APPROVAL":
                break
    with p.transaction(principal.tenant_id) as uow:
        run = uow.agent_runs.by_job(job.job_id)
    assert run and run.status == "WAITING_APPROVAL"
    VerificationCommands(p, run.agent_run_id, principal.tenant_id).prepare_simulation(
        RequestContext(principal, "synthetic-http", job.correlation_id),
        InternalReviewSimulation(tenant_id=principal.tenant_id, store=incident.store,
            agent_run_id=run.agent_run_id, source_ref="internal-review:"+str(uuid4()),
            review_record_present=True, additional_evidence_refs=run.state.evidence_refs))
    return {"session_id": str(session.session_id), "incident_id": incident.id, "store": incident.store,
        "approval_id": run.state.approval.approval_id}


if __name__ == "__main__":
    main()
