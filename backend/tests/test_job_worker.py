from datetime import timedelta

import pytest

from src.domain.jobs.models import JobRuleViolation, JobStatus, claim, finish
from src.infrastructure.jobs.job_worker import JobWorker
from tests.test_job_domain import NOW, pending


def test_expired_claim_is_recovered_with_new_attempt_and_owner():
    first = claim(pending(), NOW, "first", 10)
    second = claim(first, NOW + timedelta(seconds=10), "second", 10)
    assert second.attempt == 2
    assert second.worker_id == "second"
    with pytest.raises(JobRuleViolation):
        finish(first, NOW + timedelta(seconds=10))


def test_retryable_failure_is_delayed_and_terminal_failure_is_preserved():
    running = claim(pending(), NOW, "worker", 10)
    delayed = finish(running, NOW, failure=True, retryable=True)
    assert delayed.available_at == NOW + timedelta(seconds=5)
    assert finish(running, NOW, failure=True).status == JobStatus.FAILED


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_worker_rejects_invalid_lease(seconds):
    with pytest.raises(ValueError):
        JobWorker(None, lambda job: None, lease_seconds=seconds)
