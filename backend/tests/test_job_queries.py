from dataclasses import replace

from fastapi.testclient import TestClient

from src.api.app import create_app
from tests.test_job_domain import pending


def queue_app():
    app = create_app()
    with app.state.access_persistence.transaction("legacy-local") as uow:
        uow.jobs.save(replace(pending(), tenant_id="legacy-local", payload_ref="private-reference"))
    return app


def test_job_query_filters_permission_and_safe_contract():
    client = TestClient(queue_app())
    row = client.get("/api/v1/jobs").json()[0]
    assert row["actions"]["cancel"]["allowed"]
    assert not row["actions"]["retry"]["allowed"]
    assert "payload_ref" not in row
    assert client.get("/api/v1/jobs/job").json() == row
    assert client.get("/api/v1/jobs?status=FAILED").json() == []
    assert client.get("/api/v1/jobs?priority=P2&job_type=incident.snapshot&correlation_id=correlation").json() == [row]
    assert client.get("/api/v1/jobs?limit=101").status_code == 422
    assert client.get("/api/v1/jobs/missing").json()["error"]["code"] == "NOT_FOUND"
