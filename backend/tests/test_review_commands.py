"""검토 결정은 서버 권한·멱등성·감사 경계를 함께 거칩니다."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.application.security.principal import Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_review_queries import review_app

APPROVAL = "11111111-1111-4111-8111-111111111111"


def test_incident_execute_permission_expires_with_approval():
    app = review_app()
    client = TestClient(app)
    response = client.post(f"/api/v1/reviews/{APPROVAL}/approve", headers={"Idempotency-Key": "once"},
                           json={"reason": "확인", "expected_version": 1})
    assert response.status_code == 200
    workspace_url = "/api/v1/incidents/review-incident/workspace"
    assert client.get(workspace_url).json()["commands"]["execute"]["allowed"]
    app.state.service.clock = lambda: datetime(2026, 10, 4, tzinfo=UTC)
    permissions = client.get(workspace_url).json()
    assert not permissions["commands"]["execute"]["allowed"]
    assert not permissions["actions"]["execute"]["allowed"]
    assert "승인 기록" in permissions["commands"]["execute"]["reason"]
    assert client.post("/api/v1/incidents/review-incident/execute", json={}).status_code == 409


@pytest.mark.parametrize("decision", ["approve", "reject"])
def test_registered_reviewer_cannot_bypass_reason_via_legacy_endpoint(decision):
    app = review_app()
    app.state.identity_provider = LocalIdentityProvider({
        "registered": Principal("reviewer", "legacy-local", frozenset({Role.REVIEWER}),
                                authentication_source="local-compatibility")})
    client = TestClient(app)
    response = client.post(f"/api/v1/incidents/review-incident/{decision}",
                           headers={"Authorization": "Bearer registered", "Idempotency-Key": "legacy-once"}, json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REVIEW_COMMAND_REQUIRED"
    headers = {"Authorization": "Bearer registered"}
    workspace = client.get("/api/v1/incidents/review-incident/workspace", headers=headers).json()
    assert not workspace["commands"][decision]["allowed"]
    assert "검토 대기함" in workspace["commands"][decision]["reason"]
    assert client.get(f"/api/v1/reviews/{APPROVAL}", headers=headers).json()["approval"]["actions"][decision]["allowed"]
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert uow.approvals.get(APPROVAL).status == "PENDING"
        assert uow.audit.list() == []


@pytest.mark.parametrize("decision,status", [("approve", "APPROVED"), ("reject", "REJECTED")])
def test_review_decision_replay_and_conflict(decision, status):
    app = review_app()
    client = TestClient(app)
    url = f"/api/v1/reviews/{APPROVAL}/{decision}"
    headers = {"Idempotency-Key": "decision-once"}
    body = {"reason": "증거 확인 완료", "expected_version": 1}
    first = client.post(url, headers=headers, json=body)
    assert first.status_code == 200
    assert client.post(url, headers=headers, json=body).json() == first.json()
    assert client.post(url, headers=headers, json={**body, "reason": "다른 사유"}).json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert client.post(url, headers={"Idempotency-Key": "another"}, json=body).status_code == 409
    with app.state.access_persistence.transaction("legacy-local") as uow:
        approval = uow.approvals.get(APPROVAL)
        assert approval.status == status
        assert approval.decided_by == "local-operator"
        assert approval.decision_reason == body["reason"]
        assert len(uow.audit.list()) == 1
        assert uow.audit.list()[0].resource_type == "approval"


def test_review_role_tenant_and_required_inputs():
    app = review_app()
    app.state.identity_provider = LocalIdentityProvider({
        "read": Principal("reader", "legacy-local", frozenset({Role.AUDITOR})),
        "review": Principal("reviewer", "legacy-local", frozenset({Role.REVIEWER})),
        "other": Principal("other", "other", frozenset({Role.REVIEWER})),
    })
    client = TestClient(app)
    url = f"/api/v1/reviews/{APPROVAL}/approve"
    body = {"reason": "증거 확인", "expected_version": 1}
    for token, expected in [("read", 403), ("other", 404)]:
        response = client.post(url, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "once"}, json=body)
        assert response.status_code == expected
    assert client.get("/api/v1/reviews", headers={"Authorization": "Bearer other"}).json() == []
    headers = {"Authorization": "Bearer review", "Idempotency-Key": "once"}
    assert client.post(url, headers=headers, json={**body, "reason": " "}).status_code == 422
    assert client.post(url, headers={"Authorization": "Bearer review"}, json=body).status_code == 422
    assert client.post(url, headers=headers, json=body).status_code == 200
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert {a.result for a in uow.audit.list()} == {"DENIED", "SUCCESS"}
