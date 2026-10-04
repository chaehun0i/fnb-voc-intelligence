"""명시적인 Application 호출 전용이며 Jev/Job 자동 실행에 연결하지 않습니다."""
from datetime import UTC, datetime

from src.llm.errors import LLMError, LLMErrorCode
from src.llm.gateway import LLMGateway


class RoutedLLMExecutor:
    def __init__(self, router, *, clock=lambda: datetime.now(UTC)):
        self.router, self.clock = router, clock

    async def execute(self, intent, resolved, *, domain_validator=None):
        config = resolved.effective
        selection = self.router.select(intent, resolved)
        try:
            return await self.run(selection, intent, config, domain_validator)
        except LLMError as error:
            if not error.retryable or not (intent.fallback_allowed and config.llm_fallback_allowed):
                raise
            if (intent.deadline - self.clock()).total_seconds() <= 0:
                raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED) from None
            alternative = self.router.select(intent, resolved, fallback=True)
            if alternative.provider.capability.provider == selection.provider.capability.provider:
                raise
            result = await self.run(alternative, intent, config, domain_validator)
            return result.model_copy(update={"fallback_used": True})

    async def run(self, selection, intent, config, domain_validator):
        return await LLMGateway(selection.provider, clock=self.clock).execute(intent,
            model=selection.binding.model, timeout_seconds=selection.timeout_seconds,
            repair_limit=min(1, config.structured_output_retry), domain_validator=domain_validator,
            hosted_ai_allowed=config.hosted_ai_allowed)
