"""권한 변경·만료·최고 위험 조치 등 안전 경계의 회귀 행렬입니다."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from src.application.security.principal import Principal, Role
from src.domain.incidents.enums import Severity
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_review_queries import review_app

APPROVAL = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("changes,status", [
    ({"expires_at": "2026-10-01T09:00:00+00:00"}, 409),
    ({"action_digest": "stale"}, 409),
    ({"risk_level": Severity.CRITICAL, "requested_by": "local-operator"}, 403),
])
def test_expired_changed_or_self_critical_approval_is_denied(changes, status):
    app = review_app()
    with app.state.access_persistence.transaction("legacy-local") as uow:
        uow.approvals.save(replace(uow.approvals.get(APPROVAL), **changes))
    client = TestClient(app)
    approval = client.get("/api/v1/reviews/"+APPROVAL).json()["approval"]
    assert not approval["actions"]["approve"]["allowed"]
    assert approval["actions"]["approve"]["reason"]
    response = client.post(f"/api/v1/reviews/{APPROVAL}/approve", headers={"Idempotency-Key": "once"},
                           json={"reason": "확인", "expected_version": approval["version"]})
    assert response.status_code == status
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert uow.approvals.get(APPROVAL).status == "PENDING"
        assert not uow.incidents.get("review-incident").approved


def test_role_revocation_blocks_replay_and_headers_cannot_grant_roles():
    app = review_app()
    reviewer = Principal("actor", "legacy-local", frozenset({Role.REVIEWER}))
    provider = LocalIdentityProvider({"registered": reviewer})
    app.state.identity_provider = provider
    client = TestClient(app)
    headers = {"Authorization": "Bearer registered", "Idempotency-Key": "once"}
    body = {"reason": "확인", "expected_version": 1}
    url = f"/api/v1/reviews/{APPROVAL}/approve"
    assert client.post(url, headers=headers, json=body).status_code == 200
    provider.identities["registered"] = replace(reviewer, roles=frozenset({Role.AUDITOR}))
    response = client.post(url, headers={**headers, "X-Role": "HQ_ADMIN", "X-Tenant-ID": "other"}, json=body)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTHORIZATION_DENIED"
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert len([a for a in uow.audit.list() if a.result == "SUCCESS"]) == 1


def test_registered_account_cannot_use_legacy_missing_key_exception():
    app = review_app()
    app.state.identity_provider = LocalIdentityProvider({
        "registered": Principal("local-operator", "legacy-local", frozenset({Role.HQ_ADMIN}))})
    response = TestClient(app).post("/api/v1/incidents", headers={"Authorization": "Bearer registered"},
                                   json={"title": "확인", "severity": "HIGH", "store": "매장", "owner": "담당"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"
