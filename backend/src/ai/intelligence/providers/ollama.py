"""ai/intelligence/providers/ollama: 통합된 기능 책임, 기존 실행 계약 유지."""
import json
from urllib.parse import urlsplit

import httpx

from src.ai.intelligence.models import (
    LLMError,
    LLMErrorCode,
    LLMUsage,
    ProviderCapability,
    ProviderResponse,
)


class OllamaProvider:
    capability = ProviderCapability(provider="ollama", hosted=False)

    def __init__(self, base_url="http://127.0.0.1:11434", *, transport=None):
        parsed = urlsplit(base_url)
        # 설정을 이용한 임의 외부 전송을 막기 위해 로컬 경계를 loopback으로 제한합니다.
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise LLMError(LLMErrorCode.INVALID_REQUEST)
        self.base_url, self.transport = base_url.rstrip("/"), transport

    async def generate(self, request):
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=request.timeout_seconds,
                trust_env=False, follow_redirects=False) as client:
                response = await client.post(self.base_url + "/api/chat", json={"model": request.model,
                    "messages": [{"role": "user", "content": request.prompt}], "stream": False,
                    "format": json.loads(request.output_schema_json),
                    "options": {"temperature": 0, "num_predict": request.max_output_tokens}})
            if response.status_code != 200:
                code = LLMErrorCode.RATE_LIMITED if response.status_code == 429 else (
                    LLMErrorCode.PROVIDER_TEMPORARY if response.status_code in {500, 502, 503, 504} else LLMErrorCode.INVALID_REQUEST)
                raise LLMError(code)
            data = response.json()
            if data.get("done") is not True or type(data.get("prompt_eval_count")) is not int or type(data.get("eval_count")) is not int:
                raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE)
            return ProviderResponse(content=data["message"]["content"],
                usage=LLMUsage(input_tokens=data["prompt_eval_count"], output_tokens=data["eval_count"]),
                finish_reason="LIMIT" if data.get("done_reason") == "length" else "STOP")
        except httpx.TimeoutException:
            raise LLMError(LLMErrorCode.TIMEOUT) from None
        except httpx.TransportError:
            raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE) from None
        except (ValueError, KeyError, TypeError):
            raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE) from None
