"""API의 타입·권한·존재 은폐·필수 키·저장소 오류 회귀를 고정합니다."""
from copy import deepcopy
from dataclasses import replace

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.config.models import RuntimeConfig, config_document
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def security_app():
    admin = Principal("admin", "a", frozenset({Role.HQ_ADMIN}))
    return create_app(InMemoryIncidentRepository(), identity_provider=LocalIdentityProvider({"a": admin,
        "b": replace(admin, tenant_id="b"), "auditor": replace(admin, roles=frozenset({Role.AUDITOR})),
        "operator": replace(admin, roles=frozenset({Role.OPS_MANAGER}))}))


@pytest.mark.parametrize("patch", [{"max_tool_calls": "10"}, {"jev_enabled": 1}, {"allowed_tools": "execute_sql"}, {"secret": "never-store"}])
def test_api_type_validation_does_not_coerce_or_store_unknown_fields(patch):
    app = security_app()
    response = TestClient(app).post("/api/v1/settings/runtime", headers={"Authorization": "Bearer a", "Idempotency-Key": "typed"}, json={"expected_version": 0, "config": {**config_document(RuntimeConfig()), **patch}, "reason": "타입 검증"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "never-store" not in response.text
    assert app.state.access_persistence.memory.data == {"approvals": {}}


def test_api_missing_key_tenant_isolation_readonly_and_invalid_reason():
    app = security_app()
    http = TestClient(app)
    path = "/api/v1/settings/runtime"
    body = {"expected_version": 0, "config": config_document(RuntimeConfig()), "reason": "초기 설정"}
    headers = {"Authorization": "Bearer a"}
    assert http.post(path, headers=headers, json=body).json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
    assert http.post(path, headers={**headers, "Idempotency-Key": "save"}, json=body).status_code == 200
    before = deepcopy(app.state.access_persistence.memory.data)
    assert http.get(path+"/history", headers={"Authorization": "Bearer auditor"}).status_code == 200
    assert http.get(path, headers={"Authorization": "Bearer b"}).json()["config"]["version"] == 0
    assert app.state.access_persistence.memory.data == before
    result = http.post(path+"/rollback", headers={"Authorization": "Bearer b", "Idempotency-Key": "rollback"}, json={"target_version": 1, "expected_version": 0, "reason": "타 조직 접근"})
    assert result.status_code == 404
    assert http.post(path, headers={**headers, "Idempotency-Key": "blank"}, json={**body, "reason": "   "}).status_code == 422


def test_database_error_is_unavailable_without_internal_secret(monkeypatch):
    def reject(*args, **kwargs):
        raise psycopg.OperationalError("password=secret-internal")
    monkeypatch.setattr(psycopg, "connect", reject)
    app = create_app(PostgresIncidentRepository("not-used"))
    result = TestClient(app).get("/api/v1/settings/runtime")
    assert result.status_code == 503 and result.json()["error"]["code"] == "SETTINGS_UNAVAILABLE"
    assert "secret" not in result.text


def test_denied_audit_database_error_is_also_safe(monkeypatch):
    def reject(*args, **kwargs):
        raise psycopg.OperationalError("password=secret-internal")
    monkeypatch.setattr(psycopg, "connect", reject)
    principal = Principal("audit", "a", frozenset({Role.AUDITOR}))
    app = create_app(PostgresIncidentRepository("not-used"), identity_provider=LocalIdentityProvider(default=principal))
    result = TestClient(app).post("/api/v1/settings/runtime", headers={"Idempotency-Key": "denied"}, json={"config": config_document(RuntimeConfig()), "expected_version": 0, "reason": "권한 없는 변경"})
    assert result.status_code == 503 and result.json()["error"]["code"] == "SETTINGS_UNAVAILABLE"
    assert "secret" not in result.text


def test_domain_snapshot_freezes_supplied_collections():
    tools, roles = ["incident.get"], ["REVIEWER"]
    config = RuntimeConfig(allowed_tools=tools, required_roles=roles)
    tools.append("execute_sql")
    roles.append("AUDITOR")
    assert config.allowed_tools == ("incident.get",)
    assert config.required_roles == ("REVIEWER",)
