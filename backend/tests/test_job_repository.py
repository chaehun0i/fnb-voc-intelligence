from dataclasses import replace

import pytest

from src.application.ports.repositories import JobConflict
from src.infrastructure.job_codec import job_document, job_from_document
from src.infrastructure.repositories.approval_repository import MemoryAccessState
from src.infrastructure.repositories.job_repository import MemoryJobRepository
from tests.test_job_domain import pending


def test_memory_job_repository_tenant_version_and_filters():
    state = MemoryAccessState()
    repository = MemoryJobRepository(state, "tenant")
    job = repository.save(pending())
    assert job.version == 1
    assert repository.get(job.job_id) == job
    assert MemoryJobRepository(state, "other").get(job.job_id) is None
    assert repository.list(status="PENDING", priority="P2") == [job]
    assert repository.list(job_type="missing") == []
    assert job_from_document(job_document(job)) == job
    with pytest.raises(JobConflict):
        repository.save(pending())
    with pytest.raises(JobConflict):
        MemoryJobRepository(state, "other").save(replace(job, tenant_id="other"))
