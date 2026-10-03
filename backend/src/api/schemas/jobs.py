"""원본 payload 없이 운영에 필요한 작업 정보만 공개합니다."""
from datetime import datetime

from pydantic import BaseModel, Field

from src.api.schemas.incidents import InputModel, NonEmpty
from src.api.schemas.reviews import ActionPermission
from src.domain.jobs.models import JobPriority, JobStatus


class JobResponse(BaseModel):
    id: str
    tenant_id: str
    type: str
    status: JobStatus
    priority: JobPriority
    queued_at: datetime
    available_at: datetime
    attempts: int
    max_attempts: int
    incident_id: str | None
    correlation_id: str
    config_version: int
    version: int
    parent_job_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    lease_until: datetime | None
    error_code: str | None
    error_summary: str | None
    actions: dict[str, ActionPermission]


class JobCommandRequest(InputModel):
    reason: NonEmpty
    expected_version: int = Field(ge=1)
