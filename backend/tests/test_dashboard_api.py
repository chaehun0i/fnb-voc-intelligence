"""Dashboard 인증·오류·범위·기준 시각을 검증합니다."""
from unittest.mock import Mock

from fastapi.testclient import TestClient

from src.application.dashboard.models import DashboardUnavailable
from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_review_queries import review_app


def test_dashboard_api_auth_contract_and_window():
    app = review_app()
    app.state.identity_provider = LocalIdentityProvider({
        "a": Principal("r", "legacy-local", frozenset({Role.AUDITOR})),
        "b": Principal("r", "tenant-b", frozenset({Role.AUDITOR})),
        "none": Principal("r", "legacy-local", frozenset()),
    })
    client = TestClient(app)
    assert client.get("/api/v1/dashboard").status_code == 401
    a = client.get("/api/v1/dashboard", headers={"Authorization": "Bearer a"})
    assert a.status_code == 200
    assert a.json()["as_of"] == "2026-10-01T10:00:00+00:00"
    assert a.json()["kpis"]["pending_approvals"] == 1
    assert a.json()["integration_health"]["status"] == "NOT_IMPLEMENTED"
    assert client.get("/api/v1/dashboard", headers={"Authorization": "Bearer b"}).json()["kpis"]["pending_approvals"] == 0
    assert client.get("/api/v1/dashboard", headers={"Authorization": "Bearer none"}).status_code == 403
    invalid = client.get("/api/v1/dashboard?window=all", headers={"Authorization": "Bearer a"})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.post("/api/v1/dashboard", headers={"Authorization": "Bearer a"}).status_code == 405


def test_dashboard_failure_never_returns_mock():
    app = review_app()
    app.state.dashboard_queries.projection = Mock()
    app.state.dashboard_queries.projection.project.side_effect = DashboardUnavailable("secret DB internal")
    response = TestClient(app).get("/api/v1/dashboard")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DASHBOARD_UNAVAILABLE"
    assert "secret" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
