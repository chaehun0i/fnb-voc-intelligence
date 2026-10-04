"""실제 Route가 서버 권한·버전·상한·오류 계약을 적용합니다."""
from fastapi.testclient import TestClient

from src.application.security.principal import Principal, Role
from src.domain.config.models import RuntimeConfig, config_document
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_review_queries import review_app


def test_settings_api_current_update_history_rollback_and_validation():
    app = review_app()
    app.state.identity_provider = LocalIdentityProvider({
        "admin": Principal("admin", "legacy-local", frozenset({Role.HQ_ADMIN})),
        "auditor": Principal("auditor", "legacy-local", frozenset({Role.AUDITOR})),
    })
    headers = {"Authorization": "Bearer auditor", "Idempotency-Key": "denied"}
    client = TestClient(app)
    # 기존 테스트 IdentityProvider의 reviewer/admin 토큰을 확인합니다.
    admin = {"Authorization": "Bearer admin", "Idempotency-Key": "settings-1"}
    response = client.get("/api/v1/settings/runtime", headers=admin)
    assert response.status_code == 200
    assert response.json()["config"]["version"] == 0
    body = {"config": config_document(RuntimeConfig()), "expected_version": 0, "reason": "초기 설정"}
    saved = client.post("/api/v1/settings/runtime", headers=admin, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["config"]["version"] == 1
    assert client.post("/api/v1/settings/runtime", headers=admin, json=body).json() == saved.json()
    assert client.get("/api/v1/settings/runtime/history", headers=admin).json()["revisions"][0]["actor"]
    denied = client.post("/api/v1/settings/runtime", headers=headers, json=body)
    assert denied.status_code == 403
    invalid = client.post("/api/v1/settings/runtime", headers={**admin, "Idempotency-Key": "invalid"}, json={**body, "expected_version": 1, "config": {**body["config"], "max_tool_calls": 100}})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "CONFIG_VALIDATION_FAILED"
    assert invalid.json()["error"]["details"][0]["field"] == "max_tool_calls"
    rollback = client.post("/api/v1/settings/runtime/rollback", headers={**admin, "Idempotency-Key": "rollback"}, json={"target_version": 1, "expected_version": 1, "reason": "복원"})
    assert rollback.status_code == 200 and rollback.json()["config"]["version"] == 2
    assert client.get("/api/v1/settings/runtime").status_code == 401
    assert client.get("/api/v1/settings/runtime/history?limit=101", headers=admin).status_code == 422
