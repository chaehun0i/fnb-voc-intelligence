from dataclasses import replace

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_approval_resume import waiting_run


def test_waiting_capa_api_and_real_review_permissions():
    p, run, _ = waiting_run()
    reader = Principal("reviewer", "t", frozenset({Role.REVIEWER}))
    identity = LocalIdentityProvider({"reader": reader,
        "other": replace(reader, tenant_id="other"), "store": replace(reader, store_scope=frozenset({"elsewhere"})),
        "requester": replace(reader, principal_id="operator", roles=frozenset({Role.HQ_ADMIN}))}, environment="test")
    app = create_app(p.incidents, identity_provider=identity)
    app.state.access_persistence = p
    client = TestClient(app)
    path = "/api/v1/incidents/i/agent-runs/"+run.agent_run_id
    response = client.get(path, headers={"Authorization": "Bearer reader"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "WAITING_APPROVAL" and body["approval"]["phase"] == "WAITING_APPROVAL"
    assert body["capa_proposals"][0]["supporting_evidence_ids"] == ["review:r1", "review:r2"]
    assert not any(k in response.text for k in ("delegated_roles", "delegated_store_scope", "tenant_id", "snapshot", "raw_prompt"))
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    review = "/api/v1/reviews/"+body["approval"]["approval_id"]
    assert client.get(review, headers={"Authorization": "Bearer reader"}).json()["approval"]["actions"]["approve"]["allowed"]
    assert not client.get(review, headers={"Authorization": "Bearer requester"}).json()["approval"]["actions"]["approve"]["allowed"]
