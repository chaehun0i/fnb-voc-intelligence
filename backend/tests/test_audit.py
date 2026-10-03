"""감사 이력의 조직 범위와 트랜잭션 실패를 확인합니다."""
import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


def test_command_audit_is_atomic_and_scoped():
    app = create_app()
    client = TestClient(app)
    response = client.post("/api/v1/incidents", json={
        "title": "확인", "severity": "HIGH", "store": "강남", "owner": "담당",
    })
    assert response.status_code == 201
    with app.state.access_persistence.transaction("legacy-local") as uow:
        record = uow.audit.list()[0]
        assert record.principal_id == "local-operator"
        assert record.resource_id == response.json()["id"]
        assert record.result == "SUCCESS"
        assert not hasattr(record, "payload")
    with app.state.access_persistence.transaction("other") as uow:
        assert uow.audit.list() == []
    with pytest.raises(RuntimeError), app.state.access_persistence.transaction("legacy-local") as uow:
        uow.audit.append(record)
        raise RuntimeError("전체 롤백")
    with app.state.access_persistence.transaction("legacy-local") as uow:
        assert len(uow.audit.list()) == 1
