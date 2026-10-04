"""공식 SDK를 이 어댑터 내부에만 격리합니다. credential은 저장하지 않습니다."""
import json
import os

from google import genai
from google.genai import errors, types

from src.llm.contracts import LLMUsage, ProviderCapability, ProviderResponse
from src.llm.errors import LLMError, LLMErrorCode


class GeminiProvider:
    capability = ProviderCapability(provider="gemini", hosted=True)

    def __init__(self, *, client_factory=None):
        self.client_factory = client_factory

    async def generate(self, request):
        api_key = os.getenv("GEMINI_API_KEY")
        if self.client_factory is None and not api_key:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        options = types.HttpOptions(api_version="v1", timeout=max(1, int(request.timeout_seconds * 1000)),
            retry_options=types.HttpRetryOptions(attempts=1))
        client = self.client_factory(options) if self.client_factory else genai.Client(api_key=api_key, http_options=options)
        try:
            async with client.aio as active:
                response = await active.models.generate_content(model=request.model, contents=request.prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json",
                        response_json_schema=json.loads(request.output_schema_json), temperature=0,
                        max_output_tokens=request.max_output_tokens))
            usage = response.usage_metadata
            if usage is None or usage.prompt_token_count is None or usage.candidates_token_count is None:
                raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE)
            # reasoning/thought tokens도 총 사용량에 포함합니다.
            total = usage.total_token_count
            output = max(usage.candidates_token_count, (total or 0) - usage.prompt_token_count)
            candidates = response.candidates or []
            finish = str(candidates[0].finish_reason.value) if candidates and candidates[0].finish_reason else "UNKNOWN"
            reason = {"STOP": "STOP", "MAX_TOKENS": "LIMIT", "SAFETY": "BLOCKED"}.get(finish, "UNKNOWN")
            return ProviderResponse(content=response.text or "", usage=LLMUsage(input_tokens=usage.prompt_token_count,
                output_tokens=output), finish_reason=reason)
        except errors.APIError as error:
            code = error.code
            normalized = LLMErrorCode.RATE_LIMITED if code == 429 else (
                LLMErrorCode.PROVIDER_TEMPORARY if code in {500, 502, 503, 504} else LLMErrorCode.INVALID_REQUEST)
            raise LLMError(normalized) from None
        except TimeoutError:
            raise LLMError(LLMErrorCode.TIMEOUT) from None
