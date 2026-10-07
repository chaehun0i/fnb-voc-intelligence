from dataclasses import replace
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.ai.ax.measurement import ProductEvents, metrics
from src.api.app import create_app, demo_incidents
from src.application.security.principal import AccessError, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


def test_missing_measurement_is_not_fabricated():
    result = {m.name: m for m in metrics(demo_incidents()[0], None)}
    assert len(result) == 7
    assert all(m.status == "UNAVAILABLE" and m.value is None for m in result.values())


def test_product_event_idempotency_scope_and_rollback(history_setup):
    persistence, _, context, _ = history_setup
    context = replace(context, idempotency_key="view-event")
    events = ProductEvents(persistence, lambda: datetime.now(UTC))
    event = events.record(context, "i", "ai_brief_viewed")
    assert events.record(context, "i", "ai_brief_viewed") == event
    with pytest.raises(AccessError, match="IDEMPOTENCY_CONFLICT"):
        events.record(context, "i", "evidence_opened")
    with persistence.transaction(context.principal.tenant_id) as uow:
        assert uow.product_events.history("i") == [event]
        audits_before = len(uow.audit.list())
    with persistence.transaction("other") as uow:
        assert not uow.product_events.history("i")
    assert event.feedback_stage is None
    assert "idempotency" not in event.model_dump_json() and "principal" not in event.model_dump_json()
    with persistence.transaction(context.principal.tenant_id) as uow:
        assert len(uow.audit.list()) == audits_before  # product event is not a business command audit


def test_event_api_security_and_no_free_text_payload(history_setup):
    persistence, _, context, _ = history_setup
    identity = LocalIdentityProvider({"reader": context.principal,
        "other": replace(context.principal, tenant_id="other"),
        "store": replace(context.principal, store_scope=frozenset({"other"})),
        "audit": replace(context.principal, roles=frozenset({Role.AUDITOR}))}, environment="test")
    app = create_app(persistence.incidents, identity_provider=identity)
    app.state.access_persistence = persistence
    client, path = TestClient(app), "/api/v1/incidents/i/ax/events"
    body = {"event_type": "ai_brief_viewed"}
    headers = {"Authorization": "Bearer reader", "Idempotency-Key": "ax-event"}
    response = client.post(path, json=body, headers=headers)
    assert response.status_code == 201 and response.json()["recorded"]
    assert client.post(path, json=body, headers=headers).json() == response.json()
    assert client.post(path, json=body).status_code == 401
    for token, status in (("other", 404), ("store", 403)):
        assert client.post(path, json=body, headers=headers | {"Authorization": "Bearer "+token}).status_code == status
    assert client.post(path, json={"event_type": "recommendation_accepted"}, headers=headers | {"Authorization": "Bearer audit", "Idempotency-Key": "feedback"}).status_code == 403
    assert client.post(path, json=body | {"raw_prompt": "secret"}, headers=headers).status_code == 422
    assert client.post(path, json={"event_type": "recommendation_edited"}, headers=headers | {"Idempotency-Key": "new"}).status_code == 409


def test_feedback_stays_raw_and_does_not_mutate_incident():
    from src.application.security.principal import Principal, RequestContext
    from tests.test_capa_application import prepared
    p, run, state, _, _ = prepared()
    with p.transaction(run.tenant_id) as uow:
        before = uow.incidents.get(run.incident_id)
        uow.agent_runs.save(run.model_copy(update={"state": state}))
    principal = Principal(run.requested_by, run.tenant_id, frozenset(run.delegated_roles), frozenset(run.delegated_store_scope))
    event = ProductEvents(p).record(RequestContext(principal, "req", "corr", "feedback"), run.incident_id, "recommendation_edited")
    assert event.feedback_stage == "RAW"
    with p.transaction(run.tenant_id) as uow:
        assert uow.incidents.get(run.incident_id) == before
