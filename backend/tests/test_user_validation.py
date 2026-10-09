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
