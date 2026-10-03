"""Review는 Mock이 아니라 저장한 승인 기록에서만 조회합니다."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.api.app import create_app
from src.domain.approvals.models import Approval, action_digest
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import CorrectiveAction, Incident
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def review_app():
    item = Incident("review-incident", "INC-TEST", "검토 대상", Severity.HIGH,
                    IncidentStatus.PENDING_APPROVAL, "매장", "담당", "2026-10-01T09:00:00+00:00",
                    "2026-10-03T09:00:00+00:00", corrective_actions=[CorrectiveAction(
                        "action", "온도 확인", Severity.HIGH, "온도 안정", "기준 유지")])
    app = create_app(InMemoryIncidentRepository([item]), clock=lambda: datetime(2026, 10, 1, 10, tzinfo=UTC))
    saved = app.state.service.get(item.id)
    with app.state.access_persistence.transaction("legacy-local") as uow:
        uow.approvals.save(Approval("11111111-1111-4111-8111-111111111111", "legacy-local", item.id,
                                    ("action",), action_digest(saved), saved.version, Severity.HIGH,
                                    "requester", item.created_at, item.sla_due_at))
    return app


def test_review_projection_and_permissions():
    client = TestClient(review_app())
    listed = client.get("/api/v1/reviews")
    assert listed.status_code == 200
    approval = listed.json()[0]
    assert approval["requester"] == "requester"
    assert approval["actions"]["approve"]["allowed"]
    assert not approval["actions"]["edit"]["allowed"]
    detail = client.get("/api/v1/reviews/"+approval["id"]).json()["detail"]
    assert detail["proposed_action"] == "온도 확인"
    assert detail["evidence"] == []
    assert client.get("/api/v1/reviews/missing").status_code == 404
    assert client.get("/api/v1/reviews?status=APPROVED").json() == []
