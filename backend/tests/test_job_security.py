from dataclasses import replace

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.jobs.models import JobStatus, claim
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from tests.test_job_domain import NOW, pending


def protected_queue():
    provider = LocalIdentityProvider({
        "operator": Principal("actor", "tenant", frozenset({Role.OPS_MANAGER})),
        "reader": Principal("reader", "tenant", frozenset({Role.AUDITOR})),
        "other": Principal("actor", "other", frozenset({Role.HQ_ADMIN})),
        "store": Principal("store", "tenant", frozenset({Role.STORE_MANAGER}), frozenset({"매장 B"})),
    }, environment="test")
    app = create_app(identity_provider=provider)
    with app.state.access_persistence.transaction("tenant") as uow:
        uow.jobs.save(replace(pending(), store="매장 A"))
    return app, TestClient(app)


def test_job_tenant_rbac_and_store_scope():
    app, client = protected_queue()
    body = {"reason": "취소 확인", "expected_version": 1}
    assert client.get("/api/v1/jobs").status_code == 401
    assert client.get("/api/v1/jobs/job", headers={"Authorization": "Bearer other"}).status_code == 404
    assert client.get("/api/v1/jobs", headers={"Authorization": "Bearer other"}).json() == []
    assert client.get("/api/v1/jobs", headers={"Authorization": "Bearer store"}).json() == []
    for action in ("retry", "cancel"):
        response = client.post(f"/api/v1/jobs/job/{action}", json=body,
            headers={"Authorization": "Bearer reader", "Idempotency-Key": action})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "AUTHORIZATION_DENIED"
    with app.state.access_persistence.transaction("tenant") as uow:
        assert [item.result for item in uow.audit.list()] == ["DENIED", "DENIED"]
        assert uow.jobs.get("job").status == JobStatus.PENDING


def test_terminal_rules_missing_key_and_version():
    app, client = protected_queue()
    headers = {"Authorization": "Bearer operator"}
    body = {"reason": "취소 확인", "expected_version": 1}
    assert client.post("/api/v1/jobs/job/cancel", json=body, headers=headers).status_code == 422
    headers["Idempotency-Key"] = "command"
    assert client.post("/api/v1/jobs/job/retry", json=body, headers=headers).status_code == 409
    assert client.post("/api/v1/jobs/job/cancel", json={**body, "reason": " "}, headers=headers).status_code == 422
    response = client.post("/api/v1/jobs/job/cancel", json=body, headers=headers)
    assert response.status_code == 200
    # 이미 취소된 terminal 상태를 새 command로 재실행하지 않습니다.
    assert client.post("/api/v1/jobs/job/cancel", json={**body, "expected_version": 2},
        headers={**headers, "Idempotency-Key": "next"}).status_code == 409
    assert client.patch("/api/v1/jobs/job", json={"status": "RUNNING"}, headers=headers).status_code == 405
    with app.state.access_persistence.transaction("tenant") as uow:
        assert len([item for item in uow.audit.list() if item.result == "SUCCESS"]) == 1


def test_running_cancel_is_not_reported_as_stopped():
    app, client = protected_queue()
    with app.state.access_persistence.transaction("tenant") as uow:
        running = uow.jobs.save(claim(uow.jobs.get("job"), NOW, "worker", 60))
    response = client.post("/api/v1/jobs/job/cancel", json={"reason": "중단 요청", "expected_version": running.version},
                           headers={"Authorization": "Bearer operator", "Idempotency-Key": "running-cancel"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CANCEL_NOT_SUPPORTED_WHILE_RUNNING"
    with app.state.access_persistence.transaction("tenant") as uow:
        assert uow.jobs.get("job").status == JobStatus.RUNNING
