from src.api.app import create_app


def test_health() -> None:
    app = create_app()
    assert app.url_path_for("health") == "/api/v1/health"


from datetime import UTC, datetime
from itertools import count

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


@pytest.fixture
def client():
    identifiers = count(1)
    app = create_app(
        repository=InMemoryIncidentRepository(),
        clock=lambda: datetime(2026, 10, 1, 9, tzinfo=UTC),
        id_generator=lambda: f"incident-{next(identifiers)}",
    )
    with TestClient(app) as result:
        yield result


def create(client):
    response = client.post(
        "/api/v1/incidents",
        json={
            "title": "냉장 진열 온도 이상",
            "severity": "HIGH",
            "store": "강남점",
            "owner": "운영 담당자",
        },
    )
    assert response.status_code == 201
    return response.json()


def command(client, item, path, body=None):
    response = client.post(f"/api/v1/incidents/{item['id']}/{path}", json=body or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_http_create_list_detail_and_filter(client):
    item = create(client)
    assert item["version"] == 1
    assert item["evidence"] == [] and item["timeline"][0]["status"] == "DETECTED"
    assert client.get(
        "/api/v1/incidents?severity=HIGH&status=DETECTED&store=강남점"
    ).json() == [item]
    assert client.get("/api/v1/incidents?severity=LOW").json() == []
    assert client.get(f"/api/v1/incidents/{item['id']}").json() == item


def test_empty_list_is_real_empty_success(client):
    assert client.get("/api/v1/incidents").json() == []


def test_http_full_closed_loop_returns_nested_contract(client):
    item = create(client)
    item = command(client, item, "triage")
    item = command(client, item, "investigate")
    item = command(
        client,
        item,
        "evidence",
        {
            "evidence": {
                "id": "e1",
                "source": "온도 센서",
                "type": "TEMPERATURE",
                "summary": "8도 측정",
                "confidence": 0.9,
            }
        },
    )
    item = command(
        client,
        item,
        "rca",
        {
            "candidates": [
                {
                    "id": "r1",
                    "summary": "냉장 장비 이상",
                    "confidence": 0.8,
                    "supporting_evidence_ids": ["e1"],
                }
            ]
        },
    )
    item = command(
        client,
        item,
        "actions",
        {
            "actions": [
                {
                    "id": "a1",
                    "summary": "장비 점검",
                    "risk_level": "HIGH",
                    "expected_effect": "온도 정상화",
                    "verification_criteria": "4도 이하 유지",
                }
            ]
        },
    )
    item = command(client, item, "request-approval")
    denied = client.post(f"/api/v1/incidents/{item['id']}/execute", json={})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "DOMAIN_RULE_VIOLATION"
    item = command(client, item, "approve")
    item = command(client, item, "execute")
    assert item["status"] == "VERIFYING"
    item = command(
        client, item, "verify", {"result": "PASS", "summary": "4도 유지 확인"}
    )
    assert item["status"] == "RESOLVED"
    assert item["verification"]["id"] and item["verification"]["verified_at"]
    item = command(client, item, "close")
    assert item["status"] == "CLOSED"
    assert item["evidence"][0]["status"] == "AVAILABLE"
    assert item["root_cause_candidates"][0]["supporting_evidence_ids"] == ["e1"]
    assert item["corrective_actions"][0]["status"] == "EXECUTED"


def test_stable_error_contract_with_request_id(client):
    response = client.get(
        "/api/v1/incidents/missing", headers={"X-Request-ID": "test-request"}
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "인시던트를 찾을 수 없습니다.",
            "details": [],
        },
        "request_id": "test-request",
    }
    assert response.headers["X-Request-ID"] == "test-request"


@pytest.mark.parametrize(
    "body",
    [
        {"severity": "INVALID"},
        {"status": "CLOSED"},
        {"occurred_at": "2026-10-01T09:00:00"},
        {"expected_version": 0},
    ],
)
def test_command_validation(client, body):
    item = create(client)
    response = client.post(f"/api/v1/incidents/{item['id']}/triage", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/api/v1/incidents/{item['id']}").json() == item


def test_stale_version_and_invalid_transition_do_not_mutate(client):
    item = create(client)
    classified = command(client, item, "triage")
    response = client.post(
        f"/api/v1/incidents/{item['id']}/triage", json={"severity": "LOW"}
    )
    assert response.status_code == 409
    assert client.get(f"/api/v1/incidents/{item['id']}").json() == classified
    response = client.post(
        f"/api/v1/incidents/{item['id']}/investigate", json={"expected_version": 1}
    )
    assert response.json()["error"]["code"] == "CONFLICT"


def test_workspace_permission_and_no_arbitrary_patch(client):
    item = create(client)
    workspace = client.get(f"/api/v1/incidents/{item['id']}/workspace").json()
    assert workspace["commands"]["triage"]["allowed"]
    assert not workspace["commands"]["execute"]["allowed"]
    assert (
        client.patch(
            f"/api/v1/incidents/{item['id']}", json={"status": "CLOSED"}
        ).status_code
        == 405
    )
    assert client.get("/openapi.json").json()["paths"][
        "/api/v1/incidents/{incident_id}"
    ]["get"]["responses"]["200"]


def test_cors_allows_only_local_development_origins(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
    }
    allowed = client.options("/api/v1/incidents", headers=headers)
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    rejected = client.options(
        "/api/v1/incidents", headers={**headers, "Origin": "https://untrusted.example"}
    )
    assert "access-control-allow-origin" not in rejected.headers


def test_demo_seed_is_explicit_and_isolated():
    assert TestClient(create_app()).get("/api/v1/incidents").json() == []
    seeded = TestClient(create_app(seed_demo=True)).get("/api/v1/incidents").json()
    assert seeded[0]["id"] == "demo-incident"


def test_confidence_and_query_enum_are_validated(client):
    item = create(client)
    item = command(client, item, "triage")
    item = command(client, item, "investigate")
    response = client.post(
        f"/api/v1/incidents/{item['id']}/evidence",
        json={
            "evidence": {
                "id": "e1",
                "source": "센서",
                "type": "TEMP",
                "summary": "측정",
                "confidence": 1.5,
            },
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get("/api/v1/incidents?status=INVALID").status_code == 422
    assert client.get(f"/api/v1/incidents/{item['id']}").json()["evidence"] == []


def test_backdated_triage_is_rejected(client):
    item = create(client)
    response = client.post(
        f"/api/v1/incidents/{item['id']}/triage",
        json={
            "occurred_at": "2026-09-30T09:00:00+00:00",
        },
    )
    assert response.status_code == 409
    assert client.get(f"/api/v1/incidents/{item['id']}").json() == item
