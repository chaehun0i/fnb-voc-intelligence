from datetime import UTC, datetime, timedelta

import pytest

from src.domain.jobs.models import (
    Job,
    JobRuleViolation,
    JobStatus,
    cancel,
    claim,
    finish,
    retry,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def pending(**kwargs):
    return Job("job", "tenant", "incident.snapshot", "correlation", NOW, NOW, **kwargs)


def test_job_success_and_terminal_protection():
    running = claim(pending(), NOW, "worker", 60)
    done = finish(running, NOW + timedelta(seconds=1))
    assert done.status == JobStatus.COMPLETED
    assert running.attempt == 1
    with pytest.raises(JobRuleViolation):
        claim(done, NOW, "worker", 60)


def test_retry_preserves_failure_lineage():
    failed = finish(claim(pending(), NOW, "worker", 60), NOW, failure=True)
    retried = retry(failed, "new-job", NOW)
    assert failed.status == JobStatus.FAILED
    assert retried.status == JobStatus.PENDING
    assert retried.parent_job_id == failed.job_id
    assert retried.attempt == 0


def test_cancel_and_lease_rules():
    assert cancel(pending(), NOW).status == JobStatus.CANCELLED
    running = claim(pending(), NOW, "worker", 60)
    with pytest.raises(JobRuleViolation, match="CANCEL_NOT_SUPPORTED_WHILE_RUNNING"):
        cancel(running, NOW)
    with pytest.raises(JobRuleViolation, match="JOB_LEASE_LOST"):
        finish(running, NOW + timedelta(seconds=60))


def test_bounded_retry_and_dlq():
    running = claim(pending(max_attempts=1), NOW, "worker", 60)
    assert finish(running, NOW, failure=True, retryable=True).status == JobStatus.DLQ
    delayed = finish(claim(pending(), NOW, "worker", 60), NOW, failure=True, retryable=True)
    assert delayed.status == JobStatus.PENDING
    assert delayed.available_at > NOW
