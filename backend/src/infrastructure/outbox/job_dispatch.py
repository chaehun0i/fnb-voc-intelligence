"""대표 생성 이벤트를 독립 작업으로 전달하며 중복 전달을 흡수합니다."""
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from src.domain.jobs.models import Job, JobPriority
from src.infrastructure.outbox.worker import InvalidOutboxEvent, validate_and_log
from src.infrastructure.repositories.job_repository import PostgresJobRepository


def dispatch_job(event, repository, incident, now):
    validate_and_log(event)
    if event.event_type != "incident.created":
        return None
    if incident is None or incident.tenant_id != event.payload.get("tenant_id"):
        raise InvalidOutboxEvent("작업 대상의 조직을 확인할 수 없습니다.")
    job_id = str(uuid5(NAMESPACE_URL, "serviq:incident.snapshot:" + event.event_id))
    existing = repository.get(job_id)
    if existing is not None:
        return existing
    return repository.save(Job(
        job_id=job_id, tenant_id=incident.tenant_id, job_type="incident.snapshot",
        correlation_id=event.payload["correlation_id"], created_at=now, available_at=now,
        incident_id=incident.id, store=incident.store, payload_ref=event.event_id,
        dispatch_id=event.event_id, priority=JobPriority(incident.priority),
    ))


class PostgresJobDispatcher:
    def __init__(self, connection, incidents, clock=None):
        self.connection, self.incidents = connection, incidents
        self.clock = clock or (lambda: datetime.now(UTC))

    def __call__(self, event):
        tenant = event.payload.get("tenant_id")
        if not isinstance(tenant, str) or not tenant:
            raise InvalidOutboxEvent("이벤트 조직 정보가 필요합니다.")
        with self.connection.transaction():
            # 같은 이벤트의 동시 전달도 기존 행 확인과 생성 사이에 끼어들지 못합니다.
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (event.event_id,))
            return dispatch_job(event, PostgresJobRepository(self.connection, tenant),
                                self.incidents.get(event.incident_id, tenant_id=tenant), self.clock())
