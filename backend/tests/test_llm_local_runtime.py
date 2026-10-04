"""외부 API 없이 로컬 Gemini 기준과 RAG Gateway 연결을 검증합니다."""
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.llm.service import LLMApplication
from src.application.security.principal import Principal, Role
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.llm_config import local_llm_config
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.llm.contracts import LLMResult, LLMUsage
from src.llm.errors import LLMError, LLMErrorCode
from src.rag.gateway_generator import GatewayTextGenerator
from tests.test_llm_contracts import intent


def environment(**changes):
    return {"SERVIQ_LLM_ENABLED": "true", "MODEL": "gemini-3.5-flash-lite", **changes}


def test_local_gemini_config_and_safe_defaults():
    config = local_llm_config(environment())
    assert config.default_llm_provider == "gemini"
    assert config.hosted_ai_allowed and config.llm_enabled_providers == ("gemini",)
    assert {item.model for item in config.llm_models} == {"gemini-3.5-flash-lite"}
    assert {item.model_class for item in config.llm_models} == {"FAST", "STANDARD", "REASONING"}
    assert not config.llm_fallback_allowed and not config.auto_execute
    assert local_llm_config({}) == RuntimeConfig()
    assert "GEMINI_API_KEY" not in repr(config)


@pytest.mark.parametrize("changes,code", [
    ({"APP_ENV": "production"}, LLMErrorCode.POLICY_DENIED),
    ({"MODEL": ""}, LLMErrorCode.PROVIDER_NOT_CONFIGURED),
    ({"LLM_INPUT_USD_PER_MILLION": "-1"}, LLMErrorCode.INVALID_REQUEST),
    ({"LLM_OUTPUT_USD_PER_MILLION": "nan"}, LLMErrorCode.INVALID_REQUEST),
])
def test_invalid_local_settings(changes, code):
    with pytest.raises(LLMError) as error:
        local_llm_config(environment(**changes))
    assert error.value.code == code


def test_bootstrap_cannot_override_persisted_tenant_policy():
    persistence = AccessPersistence(InMemoryIncidentRepository())
    principal = Principal("admin", "tenant", frozenset({Role.HQ_ADMIN}))
    executor = Mock(execute=AsyncMock(return_value="result"))
    app = LLMApplication(persistence, lambda _: executor, default_config=local_llm_config(environment()))
    assert asyncio.run(app.execute(principal, intent(config_version=0))) == "result"
    assert executor.execute.call_args.args[1].effective.hosted_ai_allowed
    with persistence.transaction("tenant") as uow:
        uow.configs.append(ConfigVersion(1, "tenant", RuntimeConfig(), "호스팅 AI 차단", "admin", datetime.now(UTC)), 0)
    executor.reset_mock()
    with pytest.raises(LLMError) as error:
        asyncio.run(app.execute(principal, intent(config_version=0)))
    assert error.value.code == LLMErrorCode.INVALID_REQUEST
    executor.execute.assert_not_called()
    assert asyncio.run(app.execute(principal, intent(config_version=1))) == "result"
    assert not executor.execute.call_args.args[1].effective.hosted_ai_allowed


def test_rag_uses_gateway_only_after_input_review():
    config = local_llm_config(environment())
    executor = Mock(execute=AsyncMock(return_value=LLMResult(request_id="response", provider="gemini",
        model="gemini-3.5-flash-lite", config_version=0, structured_json='{"answer":"근거 답변 [R1]"}', usage=LLMUsage())))
    with pytest.raises(LLMError) as error:
        GatewayTextGenerator(config, executor).generate("검토하지 않은 VOC")
    assert error.value.code == LLMErrorCode.POLICY_DENIED
    executor.execute.assert_not_called()
    generator = GatewayTextGenerator(config, executor, reviewed=True)
    assert generator.generate("비식별화한 근거 [R1]") == "근거 답변 [R1]"
    assert generator.model == "gemini-3.5-flash-lite"
    value = executor.execute.call_args.args[0]
    assert value.free_text_reviewed and value.classification == "CONFIDENTIAL"
    assert not value.fallback_allowed
