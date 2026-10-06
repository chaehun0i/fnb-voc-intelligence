"""원문 없는 호출 기록의 Tenant 범위 저장·조회 계약입니다."""
from typing import Protocol

from src.ai.intelligence.models import LLMCallRecord


class LLMCallRepository(Protocol):
    def append(self, record: LLMCallRecord) -> None: ...
    def history(self, incident_id: str, limit: int = 20) -> list[LLMCallRecord]: ...


class LLMCallsUnavailable(Exception):
    """저장소 원문을 HTTP 응답에 노출하지 않습니다."""
