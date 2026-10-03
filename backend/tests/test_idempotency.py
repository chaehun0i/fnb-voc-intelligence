"""중복 결과·내용 충돌·조직 범위를 외부 서비스 없이 확인합니다."""
from fastapi.testclient import TestClient

from src.api.app import create_app


def test_duplicate_create_replays_without_duplicate_audit_or_version():
    app = create_app()
    client = TestClient(app)
    headers = {"Idempotency-Key": "create-once"}
    body = {"title": "확인", "severity": "HIGH", "store": "매장", "owner": "담당"}
    first = client.post("/api/v1/incidents", headers=headers, json=body)
    second = client.post("/api/v1/incidents", headers=headers, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    conflict = client.post("/api/v1/incidents", headers=headers, json={**body, "title": "다른 내용"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert len(client.get("/api/v1/incidents").json()) == 1
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert len(uow.audit.list()) == 1


def test_invalid_key_is_rejected():
    client = TestClient(create_app())
    assert client.get("/api/v1/incidents", headers={"Idempotency-Key": "bad key"}).status_code == 422
