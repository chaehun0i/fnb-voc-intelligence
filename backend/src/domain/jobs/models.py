"""작업 상태 전이는 외부 서비스 없이 결정적으로 검사합니다."""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DLQ = "DLQ"
    CANCELLED = "CANCELLED"


class JobPriority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class JobRuleViolation(Exception):
    def __init__(self, code="JOB_TRANSITION_NOT_ALLOWED"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Job:
    job_id: str
    tenant_id: str
    job_type: str
    correlation_id: str
    created_at: datetime
    available_at: datetime
    incident_id: str | None = None
    store: str | None = None
    payload_ref: str | None = None
    dispatch_id: str | None = None
    parent_job_id: str | None = None
    priority: JobPriority = JobPriority.P2
    status: JobStatus = JobStatus.PENDING
    attempt: int = 0
    max_attempts: int = 3
    started_at: datetime | None = None
    completed_at: datetime | None = None
    lease_until: datetime | None = None
    worker_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    version: int = 0
    config_version: int = 1
    delegated_principal_id: str | None = None
    delegated_roles: tuple[str, ...] = ()
    delegated_store_scope: tuple[str, ...] = ()

    def __post_init__(self):
        if any(not value.strip() for value in (self.job_id, self.tenant_id, self.job_type, self.correlation_id)):
            raise ValueError("작업 식별 정보는 비워 둘 수 없습니다.")
        if not 0 <= self.attempt <= self.max_attempts or self.max_attempts < 1 or self.version < 0:
            raise ValueError("시도 횟수와 버전을 확인해 주세요.")
        for value in (self.created_at, self.available_at, self.started_at, self.completed_at, self.lease_until):
            if value is not None and value.tzinfo is None:
                raise ValueError("작업 시각에는 시간대가 필요합니다.")
        object.__setattr__(self, "status", JobStatus(self.status))
        object.__setattr__(self, "priority", JobPriority(self.priority))
        object.__setattr__(self, "delegated_roles", tuple(self.delegated_roles))
        object.__setattr__(self, "delegated_store_scope", tuple(self.delegated_store_scope))
        if self.status == JobStatus.RUNNING and (not self.worker_id or self.lease_until is None):
            raise ValueError("실행 중인 작업에는 Worker와 잠금 만료 시각이 필요합니다.")


def claim(job: Job, now: datetime, worker_id: str, lease_seconds: float) -> Job:
    recovered = job.status == JobStatus.RUNNING and job.lease_until <= now
    if not worker_id.strip() or lease_seconds <= 0:
        raise ValueError("Worker와 잠금 시간을 확인해 주세요.")
    if not (job.status == JobStatus.PENDING or recovered) or job.available_at > now or job.attempt >= job.max_attempts:
        raise JobRuleViolation()
    return replace(job, status=JobStatus.RUNNING, attempt=job.attempt + 1,
                   worker_id=worker_id, lease_until=now + timedelta(seconds=lease_seconds),
                   started_at=now, completed_at=None)


def finish(job: Job, now: datetime, *, failure: bool = False, retryable: bool = False,
           retry_seconds: float = 5) -> Job:
    if job.status != JobStatus.RUNNING or job.lease_until <= now:
        raise JobRuleViolation("JOB_LEASE_LOST")
    status = JobStatus.COMPLETED
    available_at = job.available_at
    code = summary = None
    if failure:
        if retryable and job.attempt < job.max_attempts:
            status = JobStatus.PENDING
            available_at = now + timedelta(seconds=min(300, retry_seconds * 2 ** min(job.attempt - 1, 20)))
            code, summary = "TEMPORARY_FAILURE", "일시적인 실패로 재시도를 대기합니다."
        else:
            status = JobStatus.DLQ if retryable else JobStatus.FAILED
            code, summary = ("MAX_ATTEMPTS" if retryable else "PROCESSING_FAILED"), "처리에 실패했습니다. 운영 담당자의 확인이 필요합니다."
    return replace(job, status=status, available_at=available_at, lease_until=None,
                   worker_id=None, completed_at=None if status == JobStatus.PENDING else now,
                   error_code=code, error_summary=summary)


def cancel(job: Job, now: datetime) -> Job:
    if job.status == JobStatus.RUNNING:
        raise JobRuleViolation("CANCEL_NOT_SUPPORTED_WHILE_RUNNING")
    if job.status != JobStatus.PENDING:
        raise JobRuleViolation()
    return replace(job, status=JobStatus.CANCELLED, completed_at=now)


def retry(job: Job, new_id: str, now: datetime) -> Job:
    if job.status not in {JobStatus.FAILED, JobStatus.DLQ}:
        raise JobRuleViolation()
    return Job(job_id=new_id, tenant_id=job.tenant_id, job_type=job.job_type,
               correlation_id=job.correlation_id, created_at=now, available_at=now,
               incident_id=job.incident_id, store=job.store, payload_ref=job.payload_ref,
               parent_job_id=job.job_id, priority=job.priority, max_attempts=job.max_attempts,
               config_version=job.config_version, delegated_principal_id=job.delegated_principal_id,
               delegated_roles=job.delegated_roles, delegated_store_scope=job.delegated_store_scope)
