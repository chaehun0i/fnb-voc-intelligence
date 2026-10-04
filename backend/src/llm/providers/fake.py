"""네트워크 없이 명시적 응답 시퀀스로 장애와 repair를 재현합니다."""
from collections import deque

from src.llm.contracts import LLMUsage, ProviderCapability, ProviderResponse
from src.llm.errors import LLMError


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
