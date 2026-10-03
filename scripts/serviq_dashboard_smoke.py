"""전용 PostgreSQL 원본으로 Dashboard 범위·집계·실제 Worker 연결을 검증합니다."""
import os
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.approvals.models import Approval, action_digest
from src.domain.incidents.models import (
    CorrectiveAction,
    RootCauseCandidate,
    StateTransition,
)
from src.domain.jobs.models import Job
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.dashboard_projection import MemoryDashboardProjection
from src.infrastructure.migrations import migrate
from src.infrastructure.outbox.job_dispatch import PostgresJobDispatcher
from src.infrastructure.outbox.worker import OutboxEvent
from src.infrastructure.queue.runtime import snapshot_processor
from src.infrastructure.queue.worker import JobWorker
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def verify(dsn):
    migrate(dsn)
    tenant, other = "dashboard-" + uuid4().hex, "dashboard-other-" + uuid4().hex
    provider = LocalIdentityProvider({
        "admin": Principal("admin", tenant, frozenset({Role.HQ_ADMIN})),
        "east": Principal("reader", tenant, frozenset({Role.AUDITOR}), frozenset({"동부"})),
        "empty-store": Principal("store", tenant, frozenset({Role.STORE_MANAGER})),
        "other": Principal("reader", other, frozenset({Role.AUDITOR})),
        "none": Principal("none", tenant, frozenset()),
    }, environment="test")
    repo = PostgresIncidentRepository(dsn)
    app = create_app(repo, identity_provider=provider, clock=lambda: NOW)
    client = TestClient(app)

    def dashboard(token="east", status=200):
        response = client.get("/api/v1/dashboard?window=7d", headers={"Authorization": "Bearer " + token})
        assert response.status_code == status, response.text
        return response.json()

    assert dashboard()["kpis"]["open_incidents"] == 0
    assert client.get("/api/v1/dashboard").status_code == 401
    dashboard("none", 403)
    invalid = client.get("/api/v1/dashboard?window=30d", headers={"Authorization": "Bearer admin"})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    created = client.post("/api/v1/incidents", headers={"Authorization": "Bearer admin", "Idempotency-Key": uuid4().hex},
        json={"title": "Dashboard 실제 흐름", "severity": "CRITICAL", "store": "동부", "owner": "담당"})
    assert created.status_code == 201
    item = repo.get(created.json()["id"], tenant_id=tenant)
    assert dashboard()["kpis"]["open_incidents"] == 1
    with psycopg.connect(dsn, autocommit=True) as connection:
        row = connection.execute("SELECT event_id,event_type,payload FROM serviq_outbox WHERE incident_id=%s", (item.id,)).fetchone()
        event = OutboxEvent(str(row[0]), item.id, row[1], row[2], 1, 3)
        dispatcher = PostgresJobDispatcher(connection, repo, clock=lambda: NOW)
        job = dispatcher(event)
        assert dispatcher(event).job_id == job.job_id
        assert dashboard()["kpis"]["queue_depth"] == 1
        worker = JobWorker(connection, snapshot_processor(repo), tenant_id=tenant, clock=lambda: NOW)
        claim = worker.claim()
        assert claim.job_id == job.job_id
        assert dashboard()["kpis"]["queue_depth"] == 0
        assert dashboard()["kpis"]["running_jobs"] == 1
        assert worker.acknowledge(claim)
        assert dashboard()["kpis"]["running_jobs"] == 0
    boundary = repo.save(replace(item, id=str(uuid4()), version=0, severity="HIGH", created_at="2026-09-27T09:00:00+09:00",
        root_cause_candidates=[RootCauseCandidate("candidate", "공유하면 안 되는 원문", 0.8)],
        corrective_actions=[CorrectiveAction(s, "원문", "HIGH", "효과", "기준", status=s) for s in ["PROPOSED", "APPROVED", "EXECUTED"]]))
    repo.save(replace(item, id=str(uuid4()), version=0, status="CLOSED", created_at="2026-09-26T23:59:59Z",
        timeline=[StateTransition("RESOLVED", "2026-10-02T23:00:00Z"), StateTransition("CLOSED", "2026-10-03T01:00:00Z")]))
    repo.save(replace(item, id=str(uuid4()), version=0, created_at="2026-10-03T12:00:01Z"))
    repo.save(replace(item, id=str(uuid4()), version=0, store="서부"))
    foreign = repo.save(replace(item, id=str(uuid4()), version=0, tenant_id=other))
    with app.state.access_persistence.transaction(tenant) as uow:
        for target in [boundary, repo.list(store="서부", tenant_id=tenant)[0]]:
            uow.approvals.save(Approval(str(uuid4()), tenant, target.id, ("PROPOSED",), action_digest(target), target.version,
                "HIGH", "requester", "2026-10-03T00:00:00Z", "2026-10-04T00:00:00Z"))
        for state in ["PENDING", "RUNNING", "FAILED", "DLQ", "CANCELLED", "COMPLETED"]:
            uow.jobs.save(Job(str(uuid4()), tenant, "test", boundary.id, NOW, NOW + timedelta(days=1),
                incident_id=boundary.id, store="동부", status=state,
                worker_id="test" if state == "RUNNING" else None, lease_until=NOW + timedelta(seconds=60) if state == "RUNNING" else None))
        for _ in range(104):
            uow.jobs.save(Job(str(uuid4()), tenant, "test", boundary.id, NOW, NOW, store="동부"))
        uow.jobs.save(Job(str(uuid4()), tenant, "test", boundary.id, NOW, NOW, store="서부"))
    with app.state.access_persistence.transaction(other) as uow:
        uow.jobs.save(Job(str(uuid4()), other, "test", foreign.id, NOW, NOW, store="동부", status="DLQ"))
    result = dashboard()
    assert result["as_of"] == NOW.isoformat() and result["timezone"] == "UTC"
    assert result["kpis"] == {"open_incidents": 2, "critical_incidents": 1, "pending_approvals": 1,
        "failed_jobs": 1, "dlq_jobs": 1, "queue_depth": 105, "running_jobs": 1}
    assert result["incident_trend"][0] == {"day": "2026-09-27", "detected": 1, "resolved": 0}
    assert result["incident_trend"][-2]["resolved"] == 1
    assert result["incident_trend"][-1]["detected"] == 1
    assert result["root_cause_distribution"] == [{"label": "미분류", "count": 1}]
    assert [c["count"] for c in result["capa_status"]] == [1, 1, 1]
    assert result["integration_health"]["status"] == "NOT_IMPLEMENTED"
    assert dashboard("other")["kpis"]["dlq_jobs"] == 1
    assert dashboard("empty-store")["kpis"]["open_incidents"] == 0
    assert foreign.id not in str(result) and "공유하면" not in str(result)
    # 동일 fixture의 메모리 projection과 SQL projection 결과가 완전히 일치합니다.
    memory = create_app(InMemoryIncidentRepository(repo.list(tenant_id=tenant)), identity_provider=provider, clock=lambda: NOW)
    with app.state.access_persistence.transaction(tenant) as source, memory.state.access_persistence.transaction(tenant) as target:
        for approval in source.approvals.list():
            target.approvals.save(approval)
        for offset in range(0, 200, 100):
            for job in source.jobs.list(offset=offset):
                target.jobs.save(replace(job, version=0))
    projection = MemoryDashboardProjection(memory.state.access_persistence).project(provider.resolve("Bearer east"), NOW, NOW.replace(day=27, month=9, hour=0))
    assert asdict(projection) == result
    with psycopg.connect(dsn, autocommit=True) as connection:
        def state():
            return [connection.execute(f"SELECT * FROM {table} WHERE tenant_id=%s ORDER BY 1", (tenant,)).fetchall()
                    for table in ["serviq_incidents", "serviq_approvals", "serviq_jobs", "serviq_outbox", "serviq_audit", "serviq_idempotency"]]
        before = state()
        assert dashboard() == result
        assert state() == before
        # 오염된 원본의 내부 DB 오류를 fixture로 덮어쓰지 않습니다.
        connection.execute("UPDATE serviq_incidents SET document=jsonb_set(document,'{created_at}', '\"invalid-secret-date\"') WHERE id=%s", (boundary.id,))
        try:
            error = dashboard(status=503)
            assert error["error"]["code"] == "DASHBOARD_UNAVAILABLE" and "secret" not in str(error)
        finally:
            connection.execute("UPDATE serviq_incidents SET document=jsonb_set(document,'{created_at}',to_jsonb(%s::text)) WHERE id=%s", (boundary.created_at, boundary.id))
    print("[통과] 실제 Dashboard/7d/UTC/전체 집계/조직·매장 격리/RCA·CAPA/읽기 전용/오류 계약")
    print("[통과] 실제 Incident→Outbox dispatch→Job claim/완료→Dashboard 변화")


def main():
    dsn = os.getenv("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 설정해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
