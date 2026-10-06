from dataclasses import replace

from fastapi.testclient import TestClient

from src.agents.verification_commands import VerificationCommands
from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_verification_node import verifying_state


def test_actual_trace_exposes_internal_mode_not_sensitive_context():
    p, run, state = verifying_state()
    c = VerificationCommands(p, run.agent_run_id, "t", clock=lambda: run.started_at)
    c.apply(c.evaluate(state))
    reader = Principal("auditor", "t", frozenset({Role.AUDITOR}))
    identity = LocalIdentityProvider({"reader": reader, "other": replace(reader, tenant_id="other"),
        "store": replace(reader, store_scope=frozenset({"elsewhere"}))}, environment="test")
    app = create_app(p.incidents, clock=lambda: run.started_at, identity_provider=identity)
    app.state.access_persistence = p
    client = TestClient(app)
    path = "/api/v1/incidents/i/agent-runs/"+run.agent_run_id
    response = client.get(path, headers={"Authorization": "Bearer reader"})
    assert response.status_code == 200
    body = response.json()
    assert body["execution"]["execution_mode"] == "INTERNAL_RECORD_ONLY"
    assert body["verification"]["result"] == "INCONCLUSIVE"
    assert body["resulting_incident_status"] == "VERIFYING"
    assert not any(k in response.text for k in ("tenant_id", "delegated_roles", "raw_prompt", "raw_response", "snapshot", "idempotency_key"))
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.post(path, json={}, headers={"Authorization": "Bearer reader"}).status_code == 405
