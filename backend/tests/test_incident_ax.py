from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.ai.ax.models import AIBrief
from src.ai.ax.projector import project_incident
from src.api.app import create_app, demo_incidents
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


def test_empty_projection_is_honest_and_has_no_numeric_confidence():
    result = project_incident(demo_incidents()[0])
    assert result.source_run_id is None and result.coverage.evidence_count == 0
    assert result.brief.confidence_level == "INCONCLUSIVE" and result.verification_result is None
    assert result.current_phase == "DETECTED"
    assert "raw_prompt" not in result.model_dump_json()
    assert result == project_incident(replace(demo_incidents()[0], title="SECRET-PII"))


def test_ax_contract_rejects_probability_and_extra_sensitive_fields():
    for extra in ({"confidence_level": .99}, {"raw_prompt": "secret"}):
        with pytest.raises(ValidationError):
            AIBrief(headline="안내", summary="상태", **extra)


def test_ax_api_is_scoped_and_separate_from_trace(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    run, _, _ = service.prepare(job)
    identity = LocalIdentityProvider({"reader": context.principal,
        "other": replace(context.principal, tenant_id="other"),
        "store": replace(context.principal, store_scope=frozenset({"elsewhere"}))}, environment="test")
    app = create_app(persistence.incidents, identity_provider=identity)
    app.state.access_persistence = persistence
    client = TestClient(app)
    path = "/api/v1/incidents/i/ax"
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer reader"})
    assert response.status_code == 200
    assert response.json()["source_run_id"] == run.agent_run_id
    assert response.json()["decision_reference"] == decision.decision_id
    for secret in ("checkpoint", "raw_prompt", "tenant_id", "delegated_roles", "requested_by"):
        assert secret not in response.text
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.post(path, headers={"Authorization": "Bearer reader"}).status_code == 405
