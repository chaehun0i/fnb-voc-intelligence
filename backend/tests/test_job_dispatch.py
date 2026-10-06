from src.infrastructure.jobs.job_dispatch import dispatch_job
from src.infrastructure.jobs.outbox_worker import OutboxEvent
from src.infrastructure.repositories.approval_repository import MemoryAccessState
from src.infrastructure.repositories.job_repository import MemoryJobRepository
from tests.test_job_domain import NOW
from tests.test_review_queries import review_app


def test_duplicate_event_dispatch_creates_one_job():
    app = review_app()
    incident = app.state.service.get("review-incident")
    event = OutboxEvent("event-id", incident.id, "incident.created", {
        "event_id": "event-id", "event_type": "incident.created", "event_version": 1,
        "aggregate_id": incident.id, "aggregate_version": 1, "from_status": None,
        "to_status": "DETECTED", "occurred_at": NOW.isoformat(),
        "tenant_id": incident.tenant_id, "correlation_id": "chain",
    }, 1, 3)
    repository = MemoryJobRepository(MemoryAccessState(), incident.tenant_id)
    first = dispatch_job(event, repository, incident, NOW)
    assert dispatch_job(event, repository, incident, NOW) == first
    assert len(repository.list()) == 1
    assert first.correlation_id == "chain"
