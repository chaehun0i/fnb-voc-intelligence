"""기존 Incident·Review·Job 변경을 복제 테이블 없이 다음 조회에 반영합니다."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.domain.jobs.models import Job
from tests.test_review_queries import review_app


def test_existing_workflow_updates_dashboard():
    app = review_app()
    app.state.service.clock = lambda: datetime(2026, 10, 3, tzinfo=UTC)
    client = TestClient(app)
    before = client.get("/api/v1/dashboard").json()
    created = client.post("/api/v1/incidents", json={"title": "긴급 사건", "severity": "CRITICAL", "store": "매장", "owner": "담당"})
    assert created.status_code == 201
    incident = created.json()
    after = client.get("/api/v1/dashboard").json()
    assert after["kpis"]["open_incidents"] == before["kpis"]["open_incidents"] + 1
    assert after["kpis"]["critical_incidents"] == 1
    assert after["priority_incidents"][0]["id"] == incident["id"]
    assert after["incident_trend"][-1]["detected"] == 1
    app.state.service.clock = lambda: datetime(2026, 10, 1, 10, tzinfo=UTC)
    approval = client.post("/api/v1/reviews/11111111-1111-4111-8111-111111111111/approve", headers={"Idempotency-Key": "dashboard-approve"}, json={"reason": "확인 완료", "expected_version": 1})
    assert approval.status_code == 200
    app.state.service.clock = lambda: datetime(2026, 10, 3, tzinfo=UTC)
    assert client.get("/api/v1/dashboard").json()["kpis"]["pending_approvals"] == 0
    with app.state.access_persistence.transaction("legacy-local") as uow:
        uow.jobs.save(Job("flow-job", "legacy-local", "snapshot", incident["id"], datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 10, 3, tzinfo=UTC), incident_id=incident["id"], store="매장"))
    assert client.get("/api/v1/dashboard").json()["kpis"]["queue_depth"] == 1
    assert client.post("/api/v1/jobs/flow-job/cancel", headers={"Idempotency-Key": "dashboard-cancel"}, json={"reason": "검증용 작업 취소", "expected_version": 1}).status_code == 200
    assert client.get("/api/v1/dashboard").json()["kpis"]["queue_depth"] == 0
