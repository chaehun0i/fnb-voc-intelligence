"""존재 여부·매장 권한·조회 전용 API를 확인합니다."""
from dataclasses import replace

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


def test_read_api_tenant_scope_and_no_arbitrary_post(history_setup):
    persistence, service, context, decision = history_setup
    job = service.enqueue(context, "i", decision.decision_id)
    run, _, _ = service.prepare(job)
    identity = LocalIdentityProvider({"reader": context.principal,
        "other": replace(context.principal, tenant_id="other"),
        "store": replace(context.principal, store_scope=frozenset({"elsewhere"}))}, environment="test")
    app = create_app(persistence.incidents, identity_provider=identity)
    app.state.access_persistence = persistence
    client = TestClient(app)
    path = "/api/v1/incidents/i/agent-runs"
    headers = {"Authorization": "Bearer reader"}
    assert client.get(path).status_code == 401
    response = client.get(path, headers=headers)
    assert response.status_code == 200 and response.json()["runs"][0]["agent_run_id"] == run.agent_run_id
    assert "tenant_id" not in response.text and "quality" not in response.text
    assert client.get(path+"/"+run.agent_run_id, headers=headers).json()["steps"] == []
    assert client.get(path, headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.get(path+"?limit=101", headers=headers).status_code == 422
    assert client.post(path, headers=headers).status_code == 405
