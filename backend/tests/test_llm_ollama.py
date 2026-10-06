"""Ollama가 실행되지 않아도 HTTP mock으로 공통 계약을 검증합니다."""
import asyncio
import json

import httpx
import pytest

from src.ai.intelligence.models import LLMError, LLMErrorCode
from src.ai.intelligence.providers.ollama import OllamaProvider
from tests.test_llm_gemini import request


def test_ollama_contract():
    def response(req):
        body = json.loads(req.content)
        assert body["format"] == {"type": "object"} and not body["stream"]
        assert body["model"] == "configured-model"
        return httpx.Response(200, json={"message": {"content": '{"summary":"완료"}'},
            "done": True, "prompt_eval_count": 10, "eval_count": 5, "done_reason": "stop"})
    result = asyncio.run(OllamaProvider(transport=httpx.MockTransport(response)).generate(request()))
    assert result.usage.total_tokens == 15 and result.finish_reason == "STOP"


@pytest.mark.parametrize("status,code", [(429, LLMErrorCode.RATE_LIMITED), (503, LLMErrorCode.PROVIDER_TEMPORARY), (400, LLMErrorCode.INVALID_REQUEST)])
def test_safe_http_errors(status, code):
    with pytest.raises(LLMError) as error:
        asyncio.run(OllamaProvider(transport=httpx.MockTransport(lambda _: httpx.Response(status, text="SECRET"))).generate(request()))
    assert error.value.code == code and "SECRET" not in str(error.value)


def test_nonlocal_endpoint_is_rejected():
    with pytest.raises(LLMError):
        OllamaProvider("http://example.com")
