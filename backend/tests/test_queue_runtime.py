from unittest.mock import Mock

import pytest

from src.infrastructure.queue.runtime import QueueRuntime, snapshot_processor
from tests.test_job_domain import pending


def test_runtime_dispatches_then_runs_independent_job():
    outbox, jobs = Mock(), Mock()
    outbox.run_once.return_value = True
    jobs.run_once.return_value = False
    assert QueueRuntime(outbox, jobs).run_once()
    outbox.run_once.assert_called_once()
    jobs.run_once.assert_called_once()


def test_snapshot_processor_uses_tenant_and_rejects_missing_resource():
    repository = Mock()
    repository.get.return_value = None
    with pytest.raises(ValueError):
        snapshot_processor(repository)(pending())
    repository.get.assert_called_once_with(None, tenant_id="tenant")
