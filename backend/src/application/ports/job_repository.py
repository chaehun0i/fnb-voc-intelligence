"""작업 조회와 버전 보호 저장을 위한 경계입니다."""
from typing import Protocol

from src.domain.jobs.models import Job


class JobConflict(Exception):
    """다른 실행이나 운영 명령이 먼저 작업을 변경했습니다."""


class JobRepository(Protocol):
    def get(self, job_id: str) -> Job | None: ...
    def list(self, *, status=None, priority=None, job_type=None, incident_id=None,
             correlation_id=None, limit=100, offset=0) -> list[Job]: ...
    def save(self, job: Job) -> Job: ...
