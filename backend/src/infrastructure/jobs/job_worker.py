"""짧은 claim 트랜잭션과 lease fencing으로 작업을 안전하게 실행합니다."""
import math
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from src.domain.jobs.models import JobStatus, claim, finish
from src.infrastructure.job_codec import job_from_document
from src.infrastructure.repositories.job_repository import PostgresJobRepository


class RetryableJobError(Exception):
    """일시적인 실패에만 제한된 자동 재시도를 허용합니다."""


class JobWorker:
    def __init__(self, connection, processor, *, worker_id=None, clock=None,
                 lease_seconds=60, retry_seconds=5, tenant_id=None):
        if any(not math.isfinite(value) or value <= 0 for value in (lease_seconds, retry_seconds)):
            raise ValueError("잠금과 재시도 시간은 양의 유한한 값이어야 합니다.")
        self.connection, self.processor = connection, processor
        self.worker_id = worker_id or str(uuid4())
        self.clock = clock or (lambda: datetime.now(UTC))
        self.lease_seconds, self.retry_seconds = lease_seconds, retry_seconds
        self.tenant_id = tenant_id

    def claim(self):
        now = self.clock()
        with self.connection.transaction():
            exhausted = self.connection.execute("""SELECT document FROM serviq_jobs
                WHERE status='RUNNING' AND lease_until<=%s AND attempt>=max_attempts
                AND (%s::text IS NULL OR tenant_id=%s) FOR UPDATE SKIP LOCKED""",
                (now, self.tenant_id, self.tenant_id)).fetchall()
            for row in exhausted:
                job = job_from_document(row[0])
                PostgresJobRepository(self.connection, job.tenant_id).save(replace(
                    job, status=JobStatus.DLQ, lease_until=None, worker_id=None,
                    completed_at=now, error_code="MAX_ATTEMPTS",
                    error_summary="잠금 만료 후 최대 시도 횟수에 도달했습니다."))
            row = self.connection.execute("""SELECT document FROM serviq_jobs
                WHERE attempt<max_attempts AND ((status='PENDING' AND available_at<=%s)
                OR (status='RUNNING' AND lease_until<=%s))
                AND (%s::text IS NULL OR tenant_id=%s)
                ORDER BY priority,available_at,created_at,job_id LIMIT 1 FOR UPDATE SKIP LOCKED""",
                (now, now, self.tenant_id, self.tenant_id)).fetchone()
            if row is None:
                return None
            job = job_from_document(row[0])
            return PostgresJobRepository(self.connection, job.tenant_id).save(
                claim(job, now, self.worker_id, self.lease_seconds))

    def acknowledge(self, claimed, *, failure=False, retryable=False):
        now = self.clock()
        with self.connection.transaction():
            row = self.connection.execute("""SELECT document FROM serviq_jobs
                WHERE job_id=%s AND tenant_id=%s AND status='RUNNING'
                AND version=%s AND attempt=%s AND lease_until>%s FOR UPDATE""",
                (claimed.job_id, claimed.tenant_id, claimed.version, claimed.attempt, now)).fetchone()
            if row is None:
                return False
            current = job_from_document(row[0])
            if current.worker_id != self.worker_id:
                return False
            PostgresJobRepository(self.connection, claimed.tenant_id).save(
                finish(current, now, failure=failure, retryable=retryable,
                       retry_seconds=self.retry_seconds))
        return True

    def run_once(self):
        job = self.claim()
        if job is None:
            return False
        try:
            self.processor(job)
        except Exception as error:  # noqa: BLE001 - 안전한 오류만 저장하는 Worker 경계입니다.
            self.acknowledge(job, failure=True, retryable=isinstance(error, RetryableJobError))
        else:
            self.acknowledge(job)
        return True
