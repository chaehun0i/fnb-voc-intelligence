"""공식 SDK 객체는 mock 경계에서만 사용하며 실제 Gemini를 호출하지 않습니다."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.llm.contracts import ProviderRequest
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.providers.gemini import GeminiProvider


def request():
    return ProviderRequest(request_id="r", tenant_id="t", model="configured-model", prompt='{"count":1}',
        output_schema_json='{"type":"object"}', timeout_seconds=2, max_output_tokens=100)


def test_sdk_mapping_and_normalized_response():
    active = AsyncMock()
    active.models.generate_content.return_value = Mock(text='{"summary":"정상"}', candidates=[],
        usage_metadata=Mock(prompt_token_count=10, candidates_token_count=5, total_token_count=18))
    client = Mock(aio=AsyncMock())
    client.aio.__aenter__.return_value = active
    factory = Mock(return_value=client)
    result = asyncio.run(GeminiProvider(client_factory=factory).generate(request()))
    assert json.loads(result.content)["summary"] == "정상"
    assert result.usage.total_tokens == 18
    assert factory.call_args.args[0].timeout == 2000
    assert factory.call_args.args[0].retry_options.attempts == 1
    assert active.models.generate_content.call_args.kwargs["model"] == "configured-model"
    assert active.models.generate_content.call_args.kwargs["config"].response_json_schema == {"type": "object"}


def test_missing_credential_is_safe(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(LLMError) as error:
        asyncio.run(GeminiProvider().generate(request()))
    assert error.value.code == LLMErrorCode.PROVIDER_NOT_CONFIGURED


@pytest.mark.parametrize("status,code", [(429, LLMErrorCode.RATE_LIMITED), (503, LLMErrorCode.PROVIDER_TEMPORARY),
    (400, LLMErrorCode.INVALID_REQUEST), (401, LLMErrorCode.PROVIDER_NOT_CONFIGURED), (403, LLMErrorCode.PROVIDER_NOT_CONFIGURED)])
def test_sdk_errors_never_expose_provider_message(status, code):
    from google.genai.errors import APIError
    active = AsyncMock()
    active.models.generate_content.side_effect = APIError(status, {"error": {"code": status, "message": "SECRET"}})
    client = Mock(aio=AsyncMock())
    client.aio.__aenter__.return_value = active
    with pytest.raises(LLMError) as error:
        asyncio.run(GeminiProvider(client_factory=lambda _: client).generate(request()))
    assert error.value.code == code and "SECRET" not in str(error.value)
