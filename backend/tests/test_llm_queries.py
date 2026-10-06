"""사용 기록 Query는 Tenant·매장·인증을 검사하고 임의 생성 API가 없습니다."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from src.ai.intelligence.providers.fake import FakeProvider
from src.ai.intelligence.service import LLMGateway
from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from tests.test_llm_contracts import intent


def test_usage_api_scope_and_no_public_command():
    principal = Principal("reader", "a", frozenset({Role.AUDITOR}))
    provider = LocalIdentityProvider({"a": principal, "b": replace(principal, tenant_id="b"),
        "store": replace(principal, roles=frozenset({Role.STORE_MANAGER}), store_scope=frozenset({"other"}))})
    now = datetime(2026, 10, 4, tzinfo=UTC).isoformat()
    repo = InMemoryIncidentRepository([Incident("incident", "INC-1", "제목", Severity.LOW, IncidentStatus.DETECTED,
        "store", "owner", now, now, tenant_id="a")])
    app = create_app(repo, identity_provider=provider)
    def record(call):
        with app.state.access_persistence.transaction("a") as uow:
            uow.llm_calls.append(call)
    asyncio.run(LLMGateway(FakeProvider(), recorder=record).execute(intent(tenant_id="a", incident_id="incident", config_version=0), model="fake"))
    client = TestClient(app)
    path = "/api/v1/incidents/incident/llm-calls"
    result = client.get(path, headers={"Authorization": "Bearer a"})
    assert result.status_code == 200 and len(result.json()["calls"]) == 1
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer b"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.get(path+"?limit=101", headers={"Authorization": "Bearer a"}).status_code == 422
    assert client.post(path, headers={"Authorization": "Bearer a"}, json={"prompt": "SECRET"}).status_code == 405
    assert "prompt" not in result.json()["calls"][0] and "content" not in result.json()["calls"][0]
