"""명시적인 Application 호출 전용이며 Jev/Job 자동 실행에 연결하지 않습니다."""
from datetime import UTC, datetime

from src.llm.errors import LLMError, LLMErrorCode
from src.llm.gateway import LLMGateway
from src.llm.usage import ExecutionBudget


class RoutedLLMExecutor:
    def __init__(self, router, *, clock=lambda: datetime.now(UTC), recorder=None):
        self.router, self.clock = router, clock
        self.recorder = recorder

    async def execute(self, intent, resolved, *, domain_validator=None):
        config = resolved.effective
        selection = self.router.select(intent, resolved)
        budget = ExecutionBudget(min(config.token_budget, intent.token_budget), min(config.cost_budget_usd, intent.cost_budget_usd))
        try:
            return await self.run(selection, intent, config, domain_validator, budget)
        except LLMError as error:
            if not error.retryable or not (intent.fallback_allowed and config.llm_fallback_allowed):
                raise
            if (intent.deadline - self.clock()).total_seconds() <= 0:
                raise LLMError(LLMErrorCode.DEADLINE_EXHAUSTED) from None
            alternative = self.router.select(intent, resolved, fallback=True)
            if alternative.provider.capability.provider == selection.provider.capability.provider:
                raise
            result = await self.run(alternative, intent, config, domain_validator, budget, fallback=True)
            return result.model_copy(update={"fallback_used": True})

    async def run(self, selection, intent, config, domain_validator, budget, fallback=False):
        return await LLMGateway(selection.provider, clock=self.clock, recorder=self.recorder).execute(intent,
            model=selection.binding.model, timeout_seconds=selection.timeout_seconds,
            repair_limit=min(1, config.structured_output_retry), domain_validator=domain_validator,
            hosted_ai_allowed=config.hosted_ai_allowed, budget=budget,
            input_rate=selection.binding.input_usd_per_million, output_rate=selection.binding.output_usd_per_million,
            retry_limit=1, fallback=fallback)
