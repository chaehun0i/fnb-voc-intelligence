"""명시적 Application 호출은 Principal·Tenant·Config snapshot을 먼저 검증합니다."""
import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.security.principal import AccessError, Principal, Role
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.service import LLMApplication
from tests.test_llm_contracts import intent


def test_application_rbac_tenant_and_snapshot():
    persistence = AccessPersistence(InMemoryIncidentRepository())
    principal = Principal("admin", "tenant", frozenset({Role.HQ_ADMIN}))
    with persistence.transaction("tenant") as uow:
        uow.configs.append(ConfigVersion(1, "tenant", RuntimeConfig(), "처음", "admin", datetime(2026, 10, 4, tzinfo=UTC)), 0)
        uow.configs.append(ConfigVersion(2, "tenant", replace(RuntimeConfig(), token_budget=30000), "변경", "admin", datetime(2026, 10, 4, tzinfo=UTC), parent_version=1), 1)
    executor = Mock(execute=AsyncMock(return_value="result"))
    factory = Mock(return_value=executor)
    service = LLMApplication(persistence, factory)
    assert asyncio.run(service.execute(principal, intent(config_version=1))) == "result"
    assert executor.execute.call_args.args[1].effective.token_budget == 20000
    for role in (Role.AUDITOR, Role.REVIEWER, Role.STORE_MANAGER):
        with pytest.raises(AccessError):
            asyncio.run(service.execute(replace(principal, roles=frozenset({role})), intent()))
    with pytest.raises(AccessError):
        asyncio.run(service.execute(principal, intent(tenant_id="other")))
    with pytest.raises(LLMError) as error:
        asyncio.run(service.execute(principal, intent(config_version=99)))
    assert error.value.code == LLMErrorCode.INVALID_REQUEST
    assert factory.call_count == 1
