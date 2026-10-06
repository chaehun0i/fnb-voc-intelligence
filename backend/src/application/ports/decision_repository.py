"""조회는 조직 범위, 생성은 Job 경계에 한정된 판단 감사 계약입니다."""
from typing import Protocol

from src.routing.models import DecisionRecord


class DecisionRepository(Protocol):
    def get(self, decision_id: str) -> DecisionRecord | None: ...
    def by_job(self, job_id: str, ruleset: str = "1") -> DecisionRecord | None: ...
    def history(self, incident_id: str, limit: int, offset: int) -> list[DecisionRecord]: ...
    def append(self, record: DecisionRecord) -> DecisionRecord: ...


class DecisionsUnavailable(Exception):
    """저장소 오류 원문은 HTTP 응답에 전달하지 않습니다."""
