"""전용 실제 PostgreSQL에서 Job 실행·격리·멱등성·감사를 검증합니다."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.jobs.models import Job, JobPriority, JobStatus
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.migrations import migrate
from src.infrastructure.outbox.job_dispatch import PostgresJobDispatcher
from src.infrastructure.outbox.worker import OutboxEvent, OutboxWorker
from src.infrastructure.queue.runtime import snapshot_processor
from src.infrastructure.queue.worker import JobWorker
from src.infrastructure.repositories.audit_repository import PostgresAuditRepository
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)

NOW = datetime(2026, 10, 3, 9, tzinfo=UTC)


def verify(dsn):
    migrate(dsn)
    suffix = uuid4().hex
    tenant, other = "queue-" + suffix, "queue-other-" + suffix
    provider = LocalIdentityProvider({
        "operator": Principal("operator", tenant, frozenset({Role.HQ_ADMIN})),
        "reader": Principal("reader", tenant, frozenset({Role.AUDITOR})),
        "other": Principal("operator", other, frozenset({Role.HQ_ADMIN})),
    }, environment="test")

    def client():
        return TestClient(create_app(PostgresIncidentRepository(dsn), identity_provider=provider, clock=lambda: NOW))

    http = client()

    def request(method, path, body=None, token="operator", key=None, expected=200, session=None):
        headers = {"Authorization": "Bearer " + token, "X-Request-ID": "day18-queue-smoke"}
        if method == "POST":
            headers["Idempotency-Key"] = key or str(uuid4())
        response = (session or http).request(method, "/api/v1" + path, json=body, headers=headers)
        assert response.status_code == expected, (path, response.status_code, response.text)
        return response.json()

    incident = request("POST", "/incidents", {"title": "Queue 검증", "severity": "HIGH", "store": "검증 매장", "owner": "검증 담당"}, expected=201)
    with psycopg.connect(dsn, autocommit=True) as connection:
        row = connection.execute("SELECT event_id,event_type,payload FROM serviq_outbox WHERE incident_id=%s", (incident["id"],)).fetchone()
        event = OutboxEvent(str(row[0]), incident["id"], row[1], row[2], 1, 3)
        dispatcher = PostgresJobDispatcher(connection, PostgresIncidentRepository(dsn), clock=lambda: NOW)
        first = dispatcher(event)
        assert dispatcher(event) == first
        assert len(PostgresJobRepository(connection, tenant).list()) == 1
        assert first.correlation_id == incident["id"]
        # 기존 Outbox의 상태 기록은 독립 Job 상태와 섞이지 않습니다.
        outbox = OutboxWorker(connection, dispatcher)
        for _ in range(200):
            if not outbox.run_once():
                break
        assert connection.execute("SELECT status FROM serviq_outbox WHERE event_id=%s", (event.event_id,)).fetchone()[0] == "COMPLETED"
        assert PostgresJobRepository(connection, tenant).get(first.job_id).status == JobStatus.PENDING

    path = "/jobs/" + first.job_id
    request("GET", path, token="other", expected=404)
    request("POST", path + "/cancel", {"reason": "권한 검사", "expected_version": 1}, token="reader", expected=403)
    safe = request("GET", path)
    assert "payload_ref" not in safe and "worker_id" not in safe
    assert request("GET", "/jobs?status=PENDING&priority=P2&incident_id=" + incident["id"])[0]["id"] == first.job_id

    def concurrent_claim():
        with psycopg.connect(dsn, autocommit=True) as connection:
            return JobWorker(connection, lambda job: None, clock=lambda: NOW, tenant_id=tenant, lease_seconds=10).claim()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: concurrent_claim(), range(2)))
    running = next(job for job in claims if job is not None)
    assert sum(job is not None for job in claims) == 1
    with psycopg.connect(dsn, autocommit=True) as connection:
        worker = JobWorker(connection, lambda job: None, worker_id=running.worker_id,
                           clock=lambda: NOW + timedelta(seconds=10), tenant_id=tenant, lease_seconds=10)
        recovered = worker.claim()
        assert recovered.attempt == 2
        assert not worker.acknowledge(running)
        assert worker.acknowledge(recovered, failure=True)
        failed = PostgresJobRepository(connection, tenant).get(first.job_id)
        assert failed.status == JobStatus.FAILED
        assert "password" not in (failed.error_summary or "")

    body = {"reason": "일시적인 문제를 확인해 재시도합니다.", "expected_version": failed.version}
    key = "retry-" + suffix

    def same_retry(_):
        return request("POST", path + "/retry", body, key=key, session=client())

    with ThreadPoolExecutor(max_workers=2) as executor:
        replay = list(executor.map(same_retry, range(2)))
    assert replay[0] == replay[1]
    retried = replay[0]
    assert retried["parent_job_id"] == first.job_id
    assert request("POST", path + "/retry", {**body, "reason": "다른 입력"}, key=key, expected=409)["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    request("POST", path + "/retry", body, key=key, token="reader", expected=403)
    with psycopg.connect(dsn, autocommit=True) as connection:
        repository = PostgresJobRepository(connection, tenant)
        assert len([job for job in repository.list() if job.parent_job_id == first.job_id]) == 1
        audit = PostgresAuditRepository(connection, tenant).list()
        successes = [record for record in audit if record.action == "job_retry" and record.result == "SUCCESS"]
        assert len(successes) == 1
        assert successes[0].principal_id == "operator" and successes[0].resource_id == first.job_id
        assert successes[0].reason == body["reason"]
        worker = JobWorker(connection, snapshot_processor(PostgresIncidentRepository(dsn)), tenant_id=tenant)
        assert worker.run_once()
        assert repository.get(retried["id"]).status == JobStatus.COMPLETED
        assert repository.get(first.job_id).status == JobStatus.FAILED
        cancel_job = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW))

    cancel_path = "/jobs/" + cancel_job.job_id + "/cancel"
    cancel_body = {"reason": "불필요한 검증 작업을 취소합니다.", "expected_version": 1}
    cancelled = request("POST", cancel_path, cancel_body, key="cancel-" + suffix)
    assert cancelled["status"] == "CANCELLED"
    assert request("POST", cancel_path, cancel_body, key="cancel-" + suffix) == cancelled
    with psycopg.connect(dsn, autocommit=True) as connection:
        cancelled_audit = [record for record in PostgresAuditRepository(connection, tenant).list()
                           if record.action == "job_cancel" and record.resource_id == cancel_job.job_id and record.result == "SUCCESS"]
        assert len(cancelled_audit) == 1
        assert cancelled_audit[0].reason == cancel_body["reason"]
    request("POST", "/jobs/" + cancel_job.job_id + "/retry", {**cancel_body, "expected_version": 2}, expected=409)
    with psycopg.connect(dsn, autocommit=True) as connection:
        repository = PostgresJobRepository(connection, tenant)
        bounded = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW, max_attempts=1))
        worker = JobWorker(connection, lambda job: None, clock=lambda: NOW, tenant_id=tenant, lease_seconds=10)
        claimed = worker.claim()
        assert claimed.job_id == bounded.job_id
        assert worker.acknowledge(claimed, failure=True, retryable=True)
        assert repository.get(bounded.job_id).status == JobStatus.DLQ
        assert worker.claim() is None
        expired = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW, max_attempts=1))
        lost = worker.claim()
        worker.clock = lambda: NOW + timedelta(seconds=10)
        assert worker.claim() is None
        assert repository.get(expired.job_id).status == JobStatus.DLQ
        assert not worker.acknowledge(lost)
        assert PostgresJobRepository(connection, other).get(expired.job_id) is None
        delayed = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW))
        worker.clock = lambda: NOW
        current = worker.claim()
        assert current.job_id == delayed.job_id
        assert worker.acknowledge(current, failure=True, retryable=True)
        assert repository.get(delayed.job_id).available_at == NOW + timedelta(seconds=5)
        assert worker.claim() is None
        worker.clock = lambda: NOW + timedelta(seconds=5)
        retried_claim = worker.claim()
        assert retried_claim.attempt == 2
        assert worker.acknowledge(retried_claim)
        other_repository = PostgresJobRepository(connection, other)
        other_failed = other_repository.save(Job(str(uuid4()), other, "incident.snapshot", suffix, NOW, NOW, status=JobStatus.FAILED))
    other_result = request("POST", "/jobs/" + other_failed.job_id + "/retry", body={"reason": body["reason"], "expected_version": 1}, token="other", key=key)
    assert other_result["tenant_id"] == other
    with psycopg.connect(dsn, autocommit=True) as connection:
        repository = PostgresJobRepository(connection, tenant)
        rollback_job = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW))
        constraint = sql.Identifier("queue_audit_rollback_" + suffix)
        connection.execute(sql.SQL("ALTER TABLE serviq_audit ADD CONSTRAINT {} CHECK (tenant_id <> {} OR document->>'reason' IS DISTINCT FROM 'rollback-marker')").format(constraint, sql.Literal(tenant)))
        try:
            try:
                request("POST", "/jobs/" + rollback_job.job_id + "/cancel", {"reason": "rollback-marker", "expected_version": 1}, key="rollback-" + suffix)
            except psycopg.errors.CheckViolation:
                pass
            else:
                raise AssertionError("실제 Audit INSERT 오류가 전체 명령을 롤백해야 합니다.")
            assert repository.get(rollback_job.job_id).status == JobStatus.PENDING
            assert connection.execute("SELECT count(*) FROM serviq_idempotency WHERE tenant_id=%s AND key=%s", (tenant, "rollback-" + suffix)).fetchone()[0] == 0
        finally:
            connection.execute(sql.SQL("ALTER TABLE serviq_audit DROP CONSTRAINT {}").format(constraint))
        def unsafe_failure(job):
            raise RuntimeError("password=secret-material")
        assert JobWorker(connection, unsafe_failure, tenant_id=tenant, clock=lambda: NOW).run_once()
        failed_safely = repository.get(rollback_job.job_id)
        assert failed_safely.status == JobStatus.FAILED
        assert "secret-material" not in (failed_safely.error_summary or "")
        high = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW, priority=JobPriority.P1))
        normal = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW, priority=JobPriority.P2))
        low = repository.save(Job(str(uuid4()), tenant, "incident.snapshot", suffix, NOW, NOW, priority=JobPriority.P3))
        worker = JobWorker(connection, lambda job: None, tenant_id=tenant, clock=lambda: NOW)
        highest = worker.claim()
        assert highest.job_id == high.job_id and worker.acknowledge(highest)
        with psycopg.connect(dsn, autocommit=True) as other_connection:
            other_connection.execute("SET lock_timeout='2s'")
            with connection.transaction():
                connection.execute("SELECT job_id FROM serviq_jobs WHERE job_id=%s FOR UPDATE", (normal.job_id,))
                second_worker = JobWorker(other_connection, lambda job: None, tenant_id=tenant, clock=lambda: NOW)
                skipped = second_worker.claim()
                assert skipped.job_id == low.job_id
                assert second_worker.acknowledge(skipped)
        remaining = worker.claim()
        assert remaining.job_id == normal.job_id and worker.acknowledge(remaining)
    print("[통과] Job 영속화·중복 dispatch·Tenant/RBAC·동시 claim·lease 복구·늦은 ACK 차단")
    print("[통과] Retry/Cancel·영속 멱등 재전송·내용 충돌·Audit 원자 롤백·오류 원문 미노출·FAILED/DLQ·terminal 보호")


def main():
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
