"""테넌트 ID를 알고 있어도 범위를 벗어나면 조회·변경하지 못합니다."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


def principal(tenant="tenant-a", role=Role.HQ_ADMIN, scope=frozenset()):
    return Principal(str(role), tenant, frozenset({role}), scope)


@pytest.fixture
def client():
    provider = LocalIdentityProvider({
        "operator": principal(), "other": principal("tenant-b"),
        "reviewer": principal(role=Role.REVIEWER),
        "auditor": principal(role=Role.AUDITOR),
        "store": principal(role=Role.STORE_MANAGER, scope=frozenset({"강남점"})),
    })
    return TestClient(create_app(identity_provider=provider))


def auth(token):
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid4())}


def test_tenant_isolation_and_role_guard(client):
    response = client.post("/api/v1/incidents", headers=auth("operator"), json={
        "title": "온도 확인", "severity": "HIGH", "store": "강남점", "owner": "담당",
    })
    assert response.status_code == 201
    identifier = response.json()["id"]
    url = f"/api/v1/incidents/{identifier}"
    assert client.get(url, headers=auth("operator")).status_code == 200
    assert client.get(url, headers=auth("other")).status_code == 404
    assert client.get("/api/v1/incidents", headers=auth("other")).json() == []
    assert client.post(url+"/triage", headers=auth("other"), json={}).status_code == 404
    denied = client.post(url+"/triage", headers=auth("reviewer"), json={})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "AUTHORIZATION_DENIED"
    assert client.post(url+"/triage", headers=auth("operator"), json={}).status_code == 200


def test_store_scope_and_missing_authentication(client):
    assert client.get("/api/v1/incidents").status_code == 401
    response = client.post("/api/v1/incidents", headers=auth("store"), json={
        "title": "온도 확인", "severity": "HIGH", "store": "다른 매장", "owner": "담당",
    })
    assert response.status_code == 403
    assert client.get("/api/v1/health").status_code == 200
