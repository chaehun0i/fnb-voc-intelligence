from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.ai.ax.validation import ValidationSession, validation_task


def session(**changes):
    now = datetime(2026, 10, 9, tzinfo=UTC)
    values = {"session_id": uuid4(), "tenant_id": "tenant", "store_id": "store",
        "scenario_id": "happy_path", "participant_ref": uuid4(), "started_at": now,
        "created_at": now, "validation_kind": "SYNTHETIC"}
    return ValidationSession(**(values | changes))


def test_session_is_opaque_immutable_and_business_task():
    item = session()
    assert item.consent_scope == "TASK_EVENTS_ONLY"
    assert validation_task("happy_path").expected_terminal_state == "RESOLVED"
    assert "Checkpoint" not in validation_task("happy_path").business_goal
    with pytest.raises(ValidationError):
        item.status = "COMPLETED"
    with pytest.raises(ValidationError):
        session(participant_ref="person@example.com")
    with pytest.raises(ValidationError):
        session(raw_prompt="secret")


@pytest.mark.parametrize("changes", [{"status": "COMPLETED"},
    {"started_at": "2026-01-01T00:00:00"},
    {"status": "ABANDONED", "completed_at": datetime(2026, 10, 8, tzinfo=UTC)}])
def test_session_rejects_incoherent_timestamps(changes):
    with pytest.raises(ValidationError):
        session(**changes)


def test_terminal_session_requires_real_terminal_time():
    item = session()
    completed = session(status="COMPLETED", completed_at=item.started_at + timedelta(seconds=20))
    assert completed.completed_at > completed.started_at


def test_journey_dedup_order_and_server_decision_receipt():
    from src.ai.ax.models import ProductEvent
    from src.ai.ax.validation import project_journey
    s = session()
    event = ProductEvent(event_id=str(uuid4()), tenant_id=s.tenant_id, incident_id="i", source_run_id=None,
        event_type="ai_brief_viewed", occurred_at=s.started_at, session_id=s.session_id,
        task_id="incident-understanding", milestone="DECISION_SUBMITTED")
    empty = project_journey(s, [event, event])
    assert not empty.milestones and not empty.task_success
    decision_at = s.started_at + timedelta(seconds=15)
    real = project_journey(s, [event], decision_at=decision_at)
    assert len(real.milestones) == 1 and real.milestones[0].occurred_at == decision_at
    wrong = event.model_copy(update={"tenant_id": "other"})
    with pytest.raises(ValueError, match="SCOPE"):
        project_journey(s, [wrong])


def test_journey_preserves_final_domain_outcome_without_pageview_success():
    from src.ai.ax.projector import project_incident
    from src.ai.ax.validation import project_journey
    from src.api.app import demo_incidents
    ax = project_incident(demo_incidents()[0], None)
    for status in ("RESOLVED", "REOPENED", "VERIFYING"):
        result = project_journey(session(), [], ax.model_copy(update={"current_phase": status}))
        assert result.incident_status == status and not result.task_success


def validation_client(history_setup):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.application.security.principal import Role
    from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
    persistence, _, context, _ = history_setup
    identity = LocalIdentityProvider({"owner": context.principal,
        "other": replace(context.principal, tenant_id="other"),
        "store": replace(context.principal, store_scope=frozenset({"other"})),
        "auditor": replace(context.principal, roles=frozenset({Role.AUDITOR})),
        "peer": replace(context.principal, principal_id="another")}, environment="test")
    app = create_app(persistence.incidents, identity_provider=identity)
    app.state.access_persistence = persistence
    return TestClient(app), persistence, context


def test_validation_api_consent_scope_idempotency_and_payload(history_setup):
    client, p, context = validation_client(history_setup)
    with p.transaction(context.principal.tenant_id) as uow:
        store = uow.incidents.get("i").store
    headers = {"Authorization": "Bearer owner", "Idempotency-Key": "session"}
    path = "/api/v1/validation/sessions"
    body = {"store": store, "scenario_id": "happy_path", "consent": True}
    assert client.post(path, json=body | {"consent": False}, headers=headers).status_code == 422
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert client.post(path, json=body, headers=headers).json() == response.json()
    sid = response.json()["session_id"]
    for token, status in (("other", 404), ("store", 403), ("peer", 403)):
        assert client.get(path+"/"+sid, headers={"Authorization": "Bearer "+token}).status_code == status
    event_path = path+"/"+sid+"/events"
    event = {"surface": "INCIDENT", "milestone": "INCIDENT_OPENED", "incident_id": "i"}
    eh = headers | {"Idempotency-Key": "event"}
    result = client.post(event_path, json=event, headers=eh)
    assert result.status_code == 201, result.text
    assert client.post(event_path, json=event, headers=eh).json() == result.json()
    assert client.post(event_path, json=event | {"friction": "BACKTRACK"}, headers=eh).status_code == 409
    assert client.post(event_path, json=event | {"raw_prompt": "credential"}, headers=eh).status_code == 422
    assert client.post(event_path, content=b" " * 5000, headers=eh | {"Content-Type": "application/json"}).status_code == 413
    assert client.post(event_path, json={"surface": "REVIEW", "milestone": "DECISION_SUBMITTED"}, headers=eh | {"Idempotency-Key": "decision"}).status_code == 409
    assert client.post(event_path, json=event, headers=eh | {"Authorization": "Bearer auditor"}).status_code == 403
    view = client.get(path+"/"+sid, headers=headers).json()
    assert len(view["journey"]["milestones"]) == 1 and not view["journey"]["task_success"]
    assert "principal_id" not in response.text


def test_abandon_is_not_task_success_and_events_cannot_restart(history_setup):
    from dataclasses import replace

    from src.application.user_validation import UserValidation, ValidationSignal
    p, _, context, _ = history_setup
    with p.transaction(context.principal.tenant_id) as uow:
        store = uow.incidents.get("i").store
    start = UserValidation(p, replace(context, idempotency_key="start"))
    item = start.start(store, "abandon", consent=True)
    svc = UserValidation(p, replace(context, idempotency_key="abandon"))
    body = ValidationSignal(surface="INCIDENT", friction="TASK_ABANDONED")
    event = svc.signal(item.session_id, body)
    assert svc.signal(item.session_id, body) == event
    view = svc.get(item.session_id)
    assert view["session"].status == "ABANDONED" and not view["journey"].task_success


def test_validation_metrics_empty_small_sample_and_real_duration():
    from src.ai.ax.measurement import validation_metrics
    from src.ai.ax.validation import project_journey
    assert all(m.value is None and m.sample_size == 0 and m.availability == "UNAVAILABLE"
        for m in validation_metrics([]))
    s = session(status="ABANDONED", completed_at=session().started_at + timedelta(seconds=30))
    row = {"session": s, "journey": project_journey(s, []), "events": [], "ax": None}
    result = {m.name: m for m in validation_metrics([row])}
    assert result["task_completion_rate"].value == 0
    assert result["task_completion_rate"].sample_size == 1
    assert result["task_completion_rate"].availability == "INSUFFICIENT_SAMPLE"
    assert result["median_task_duration"].value is None
    assert result["time_to_first_useful_evidence"].value is None
    row["first_evidence_at"] = s.started_at + timedelta(seconds=7)
    measured = {m.name: m for m in validation_metrics([row])}
    assert measured["time_to_first_useful_evidence"].value == 7
    assert measured["time_to_first_useful_evidence"].unit == "seconds"


def test_summary_requires_admin_and_separates_synthetic(history_setup):
    from dataclasses import replace

    from src.application.security.principal import Role
    from src.application.user_validation import UserValidation
    p, _, context, _ = history_setup
    with p.transaction(context.principal.tenant_id) as uow:
        store = uow.incidents.get("i").store
    admin = replace(context, principal=replace(context.principal, roles=frozenset({Role.HQ_ADMIN})), idempotency_key="summary-start")
    svc = UserValidation(p, admin)
    svc.start(store, "happy_path", consent=True, kind="SYNTHETIC")
    assert svc.summary(store, "SYNTHETIC")["sessions"] == 1
    assert svc.summary(store, "USER_OBSERVATION")["sessions"] == 0


@pytest.mark.parametrize("name", ["fnb_voc", "customer_prod", ""])
def test_synthetic_fixture_refuses_operating_database(name):
    from src.ai.ax.validation import validate_synthetic_database_name
    with pytest.raises(ValueError, match="EXPLICIT_TEST_DATABASE"):
        validate_synthetic_database_name(name)


def test_feedback_is_raw_bound_to_existing_artifact_and_no_domain_mutation():
    from src.application.security.principal import Principal, RequestContext
    from src.application.user_validation import UserValidation, ValidationSignal
    from tests.test_capa_application import prepared
    p, run, state, _, _ = prepared()
    principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles), frozenset(run.delegated_store_scope))
    ctx = RequestContext(principal, "test", "validation", "start")
    with p.transaction(run.tenant_id) as uow:
        before = uow.incidents.get(run.incident_id)
    item = UserValidation(p, ctx).start(before.store, "happy_path", consent=True)
    from dataclasses import replace
    svc = UserValidation(p, replace(ctx, idempotency_key="feedback"))
    body = ValidationSignal(surface="INCIDENT", incident_id=run.incident_id, feedback_decision="EDIT", artifact_type="RCA")
    event = svc.signal(item.session_id, body)
    assert svc.signal(item.session_id, body) == event
    assert event.feedback_stage == "RAW" and event.feedback_decision == "EDIT"
    assert event.artifact_id == state.rca_candidates[0].candidate_id
    assert event.source_run_id == run.agent_run_id and event.session_id == item.session_id
    with p.transaction(run.tenant_id) as uow:
        assert uow.incidents.get(run.incident_id) == before
        assert len(uow.product_events.session_events(item.session_id)) == 1
    with pytest.raises(ValidationError):
        ValidationSignal(surface="INCIDENT", milestone="FEEDBACK_SUBMITTED")


def test_completed_receipt_survives_later_incident_changes():
    from src.ai.ax.validation import project_journey
    s = session(status="COMPLETED", completed_at=session().started_at + timedelta(seconds=30), completed_phase="RESOLVED")
    result = project_journey(s, [])
    assert result.task_success and result.incident_status == "RESOLVED"
