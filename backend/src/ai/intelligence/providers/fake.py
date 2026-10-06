"""ai/intelligence/providers/fake: 통합된 기능 책임, 기존 실행 계약 유지."""
from collections import deque

from src.ai.intelligence.models import (
    LLMError,
    LLMUsage,
    ProviderCapability,
    ProviderResponse,
)


class FakeProvider:
    capability = ProviderCapability(provider="fake", hosted=False)

    def __init__(self, outcomes=()):
        self.outcomes = deque(outcomes)
        self.call_count = 0

    async def generate(self, request):
        self.call_count += 1
        outcome = self.outcomes.popleft() if self.outcomes else '{"summary":"검증 완료"}'
        if isinstance(outcome, LLMError):
            raise outcome
        if isinstance(outcome, Exception):
            raise outcome
        return ProviderResponse(content=outcome, usage=LLMUsage(input_tokens=10, output_tokens=5), finish_reason="STOP")
