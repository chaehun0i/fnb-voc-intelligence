from dataclasses import replace

import psycopg
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


def test_empty_history_and_latest_are_not_mock_fallback():
    repo, persistence, _, _ = setup_shadow()
    provider = LocalIdentityProvider({"a": Principal("read", "t", frozenset({Role.AUDITOR}))}, environment="test")
    app = create_app(repo, identity_provider=provider)
    app.state.access_persistence = persistence
    http = TestClient(app)
    headers = {"Authorization": "Bearer a"}
    path = "/api/v1/incidents/i/decisions"
    assert http.get(path, headers=headers).json() == {"decisions": [], "limit": 20, "offset": 0, "has_more": False}
    assert http.get(path+"/latest", headers=headers).json() is None
    assert http.get(path+"?offset=10001", headers=headers).status_code == 422
    assert http.get("/api/v1/incidents/missing/decisions", headers=headers).status_code == 404


def test_storage_failure_is_safe_and_never_returns_mock(monkeypatch):
    repo, persistence, _, _ = setup_shadow()
    provider = LocalIdentityProvider({"a": Principal("read", "t", frozenset({Role.AUDITOR}))}, environment="test")
    app = create_app(repo, identity_provider=provider)
    app.state.access_persistence = persistence
    def unavailable(_tenant):
        raise psycopg.OperationalError("credential secret-internal")
    monkeypatch.setattr(persistence, "transaction", unavailable)
    response = TestClient(app).get("/api/v1/incidents/i/decisions", headers={"Authorization": "Bearer a", "X-Request-ID": "request-safe"})
    assert response.status_code == 503 and response.json()["error"]["code"] == "DECISIONS_UNAVAILABLE"
    assert response.json()["request_id"] == "request-safe" and "secret" not in response.text
