"""Provider 오류와 객체가 Application 밖으로 새지 않는 비동기 코어입니다."""
import asyncio
from datetime import UTC, datetime

from src.llm.contracts import LLMResult, LLMUsage, ProviderRequest
from src.llm.data_policy import evaluate_policy
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.structured import schema_validator, validate_output


class LLMGateway:
    def __init__(self, provider, *, clock=lambda: datetime.now(UTC)):
        self.provider = provider
        self.clock = clock

    async def execute(self, intent, *, model, timeout_seconds=60, repair_limit=0, domain_validator=None, hosted_ai_allowed=False):
        policy = evaluate_policy(intent, self.provider.capability, hosted_ai_allowed=hosted_ai_allowed)
        validator = schema_validator(intent.output_schema_json)
        remaining = (intent.deadline - self.clock()).total_seconds()
        if remaining <= 0:
            raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED)
        request = ProviderRequest(request_id=intent.request_id, tenant_id=intent.tenant_id,
            model=model, prompt=policy.payload_json, output_schema_json=intent.output_schema_json,
            timeout_seconds=min(timeout_seconds, remaining), max_output_tokens=intent.max_output_tokens)
        response = await self.invoke(request)
        usage = response.usage
        repairs = 0
        try:
            structured = validate_output(response.content, validator, domain_validator)
        except LLMError as error:
            if error.code != LLMErrorCode.OUTPUT_SCHEMA_INVALID or repair_limit <= 0:
                raise
            remaining = (intent.deadline - self.clock()).total_seconds()
            if remaining <= 0:
                raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED) from None
            if usage.total_tokens + intent.max_output_tokens > intent.token_budget:
                raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED) from None
            # 잘못된 응답 원문을 다시 복제하지 않고 원래 최소 입력만 재사용합니다.
            request = request.model_copy(update={"repair": True, "timeout_seconds": min(timeout_seconds, remaining)})
            response = await self.invoke(request)
            repairs = 1
            usage = LLMUsage(input_tokens=usage.input_tokens + response.usage.input_tokens,
                output_tokens=usage.output_tokens + response.usage.output_tokens)
            structured = validate_output(response.content, validator, domain_validator)
        return LLMResult(request_id=intent.request_id, provider=self.provider.capability.provider,
            model=model, config_version=intent.config_version, structured_json=structured, usage=usage,
            structured_retry_count=repairs)

    async def invoke(self, request):
        try:
            return await asyncio.wait_for(self.provider.generate(request), timeout=request.timeout_seconds)
        except LLMError:
            raise
        except TimeoutError:
            raise LLMError(LLMErrorCode.TIMEOUT) from None
        except Exception:  # noqa: BLE001 — SDK의 미등록 예외도 원문 노출 없이 실패로 반환합니다.
            raise LLMError(LLMErrorCode.PROVIDER_UNAVAILABLE) from None
