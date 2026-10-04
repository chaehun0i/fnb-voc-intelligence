from dataclasses import replace

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_jev_shadow import setup_shadow


def test_decision_api_is_readonly_bounded_and_tenant_store_safe():
    repo, persistence, job, shadow = setup_shadow()
    shadow.record(job)
    admin = Principal("read", "t", frozenset({Role.AUDITOR}))
    provider = LocalIdentityProvider({"a": admin, "b": replace(admin, tenant_id="other"),
        "store": replace(admin, roles=frozenset({Role.STORE_MANAGER}), store_scope=frozenset({"elsewhere"}))}, environment="test")
    app = create_app(repo, identity_provider=provider)
    app.state.access_persistence = persistence
    http = TestClient(app)
    path = "/api/v1/incidents/i/decisions"
    assert http.get(path).status_code == 401
    result = http.get(path, headers={"Authorization": "Bearer a"})
    assert result.status_code == 200 and len(result.json()["decisions"]) == 1
    assert "input_digest" not in result.text and "tenant_id" not in result.text and "고객 이름" not in result.text
    assert http.get(path+"/latest", headers={"Authorization": "Bearer a"}).json()["mode"] == "SHADOW"
    assert http.get(path, headers={"Authorization": "Bearer b"}).status_code == 404
    assert http.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert http.get(path+"?limit=101", headers={"Authorization": "Bearer a"}).status_code == 422
    assert http.post(path, headers={"Authorization": "Bearer a"}).status_code == 405
