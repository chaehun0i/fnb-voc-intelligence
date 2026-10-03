from dataclasses import replace

from fastapi.testclient import TestClient

from src.domain.jobs.models import JobStatus
from tests.test_job_queries import queue_app


def test_cancel_audit_and_idempotent_replay():
    app = queue_app()
    client = TestClient(app)
    request = {"reason": "중복 작업을 중단합니다.", "expected_version": 1}
    headers = {"Idempotency-Key": "cancel-once"}
    first = client.post("/api/v1/jobs/job/cancel", json=request, headers=headers)
    assert first.status_code == 200
    assert first.json()["status"] == "CANCELLED"
    assert client.post("/api/v1/jobs/job/cancel", json=request, headers=headers).json() == first.json()
    conflict = client.post("/api/v1/jobs/job/cancel", json={**request, "reason": "다른 사유"}, headers=headers)
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert len(uow.audit.list()) == 1
        assert uow.audit.list()[0].action == "job_cancel"


def test_retry_creates_new_lineage_once():
    app = queue_app()
    with app.state.access_persistence.transaction("legacy-local") as uow:
        original = uow.jobs.save(replace(uow.jobs.get("job"), status=JobStatus.DLQ))
    client = TestClient(app)
    body = {"reason": "실패 원인을 확인하고 재시도합니다.", "expected_version": original.version}
    headers = {"Idempotency-Key": "retry-once"}
    response = client.post("/api/v1/jobs/job/retry", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["parent_job_id"] == "job"
    assert client.post("/api/v1/jobs/job/retry", json=body, headers=headers).json() == response.json()
    assert client.get("/api/v1/jobs/job").json()["status"] == "DLQ"
    assert len(client.get("/api/v1/jobs").json()) == 2
