"""Provider 오류와 객체가 Application 밖으로 새지 않는 비동기 코어입니다."""
import asyncio
from datetime import UTC, datetime

from src.llm.contracts import LLMResult, ProviderRequest
from src.llm.errors import LLMError, LLMErrorCode


class LLMGateway:
    def __init__(self, provider, *, clock=lambda: datetime.now(UTC)):
        self.provider = provider
        self.clock = clock

    async def execute(self, intent, *, model, timeout_seconds=60):
        remaining = (intent.deadline - self.clock()).total_seconds()
        if remaining <= 0:
            raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED)
        request = ProviderRequest(request_id=intent.request_id, tenant_id=intent.tenant_id,
            model=model, prompt=intent.payload_json, output_schema_json=intent.output_schema_json,
            timeout_seconds=min(timeout_seconds, remaining), max_output_tokens=intent.max_output_tokens)
        response = await self.invoke(request)
        return LLMResult(request_id=intent.request_id, provider=self.provider.capability.provider,
            model=model, config_version=intent.config_version, structured_json=response.content, usage=response.usage)

    async def invoke(self, request):
        try:
            return await asyncio.wait_for(self.provider.generate(request), timeout=request.timeout_seconds)
        except LLMError:
            raise
        except TimeoutError:
            raise LLMError(LLMErrorCode.TIMEOUT) from None
        except Exception:  # noqa: BLE001 — SDK의 미등록 예외도 원문 노출 없이 실패로 반환합니다.
            raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE) from None
