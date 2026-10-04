"""실제 DB에 Fake/SDK mock 사용 기록을 저장합니다. 외부 모델 호출·비용은 없습니다."""
import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.llm.service import LLMApplication
from src.application.security.principal import Principal, Role
from src.domain.config.models import ConfigVersion, LLMModelBinding, RuntimeConfig
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.llm.contracts import LLMIntent
from src.llm.execution import RoutedLLMExecutor
from src.llm.gateway import LLMGateway
from src.llm.providers.fake import FakeProvider
from src.llm.providers.gemini import GeminiProvider
from src.llm.router import ProviderRouter


def verify(dsn):
    migrate(dsn)
    migrate(dsn)
    now = datetime(2026, 10, 4, tzinfo=UTC)
    tenant = "llm-" + uuid4().hex
    principal = Principal("llm-admin", tenant, frozenset({Role.HQ_ADMIN}))
    repo = PostgresIncidentRepository(dsn)
    incident = repo.save(Incident(str(uuid4()), "LLM-SMOKE", "기존 업무 보존", Severity.LOW,
        IncidentStatus.DETECTED, "검증 매장", "담당", now.isoformat(), now.isoformat(), tenant_id=tenant))
    persistence = AccessPersistence(repo)
    config = replace(RuntimeConfig(), hosted_ai_allowed=True, llm_enabled_providers=("gemini",),
        llm_models=(LLMModelBinding("gemini", "STANDARD", "mock-configured-model", 1, 2),))
    with persistence.transaction(tenant) as uow:
        uow.configs.append(ConfigVersion(1, tenant, config, "LLM 계약 검증", principal.principal_id, now), 0)
    value = LLMIntent(request_id="llm-probe", correlation_id="safe-correlation", tenant_id=tenant,
        incident_id=incident.id, task_type="SUMMARY", payload_json='{"count":1,"email":"PII-SENTINEL"}',
        output_schema_json='{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
        schema_version="1", prompt_template="safe-summary", prompt_version="1", config_version=1,
        deadline=now+timedelta(minutes=10), classification="PII", free_text_reviewed=True)
    active = AsyncMock()
    active.models.generate_content.side_effect = [Mock(text="{}", candidates=[], usage_metadata=Mock(prompt_token_count=10, candidates_token_count=5, total_token_count=15)),
        Mock(text='{"summary":"RESPONSE-SENTINEL"}', candidates=[], usage_metadata=Mock(prompt_token_count=10, candidates_token_count=5, total_token_count=15))]
    client = Mock(aio=AsyncMock())
    client.aio.__aenter__.return_value = active
    provider = GeminiProvider(client_factory=lambda _: client)
    router = ProviderRouter({"gemini": provider})
    application = LLMApplication(persistence, lambda record: RoutedLLMExecutor(router, clock=lambda: now, recorder=record))
    result = asyncio.run(application.execute(principal, value))
    assert result.structured_retry_count == 1 and result.usage.total_tokens == 30
    assert all("PII-SENTINEL" not in item.kwargs["contents"] for item in active.models.generate_content.call_args_list)
    def record(call):
        with persistence.transaction(tenant) as uow:
            uow.llm_calls.append(call)
    asyncio.run(LLMGateway(FakeProvider(), clock=lambda: now, recorder=record).execute(value.model_copy(update={"request_id": "fake-probe"}), model="fake-v1"))
    identity = LocalIdentityProvider({"a": principal, "b": replace(principal, tenant_id=tenant+"-other"),
        "store": replace(principal, roles=frozenset({Role.STORE_MANAGER}), store_scope=frozenset({"다른 매장"}))}, environment="test")
    client = TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=identity))
    path = f"/api/v1/incidents/{incident.id}/llm-calls"
    response = client.get(path, headers={"Authorization": "Bearer a"})
    assert response.status_code == 200 and len(response.json()["calls"]) == 3
    assert "PII-SENTINEL" not in response.text and "RESPONSE-SENTINEL" not in response.text
    assert client.get(path, headers={"Authorization": "Bearer b"}).status_code == 404
    assert client.get(path, headers={"Authorization": "Bearer store"}).status_code == 403
    assert client.get(path).status_code == 401
    assert repo.get(incident.id) == incident
    with persistence.transaction(tenant+"-other") as uow:
        assert uow.llm_calls.history(incident.id) == []
    with psycopg.connect(dsn) as connection:
        document = connection.execute("SELECT document FROM serviq_llm_calls WHERE tenant_id=%s", (tenant,)).fetchone()[0]
        assert "prompt" not in document and "content" not in document
        for verb in ("UPDATE serviq_llm_calls SET config_version=config_version", "DELETE FROM serviq_llm_calls"):
            try:
                with connection.transaction():
                    connection.execute(verb + " WHERE tenant_id=%s", (tenant,))
            except psycopg.errors.RaiseException:
                pass
            else:
                raise AssertionError("불변 사용 기록의 변경이 허용되었습니다.")
    print(json.dumps({"llm_gateway": "passed", "calls": 3, "external_model_calls": 0}))


def main():
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("검증 전용 SERVIQ_TEST_DATABASE_URL이 필요합니다.")
    verify(dsn)


if __name__ == "__main__":
    main()
