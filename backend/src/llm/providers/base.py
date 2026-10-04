"""Domain/Workflow가 SDK 예외와 객체를 알 필요 없는 실행 계약입니다."""
from typing import Protocol

from src.llm.contracts import ProviderCapability, ProviderRequest, ProviderResponse


class LLMProvider(Protocol):
    capability: ProviderCapability

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
