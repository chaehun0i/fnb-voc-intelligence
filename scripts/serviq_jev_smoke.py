"""실제 PostgreSQL에서 Shadow 판단·중복 전달·Tenant·불변 감사를 검증합니다."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql

from src.ai.decision.service import ShadowDecisions
from src.api.app import create_app
from src.application.security.principal import Principal, Role
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Evidence, Incident
from src.domain.jobs.models import Job, JobStatus
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider
from src.infrastructure.jobs.job_worker import JobWorker
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.migrations import migrate
from src.infrastructure.repositories.job_repository import PostgresJobRepository
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def verify(dsn):
    migrate(dsn)
    migrate(dsn)
    now = datetime(2026, 10, 4, 9, tzinfo=UTC)
    tenant, other = "jev-"+uuid4().hex, "jev-other-"+uuid4().hex
    repo = PostgresIncidentRepository(dsn)
    persistence = AccessPersistence(repo)
    principal = Principal("auditor", tenant, frozenset({Role.AUDITOR}))
    provider = LocalIdentityProvider({"reader": principal, "other": replace(principal, tenant_id=other),
        "store": replace(principal, roles=frozenset({Role.STORE_MANAGER}), store_scope=frozenset({"elsewhere"}))}, environment="test")
    incident = Incident(str(uuid4()), "JEV-SMOKE", "PII-SENTINEL secret customer@example.com", Severity.MEDIUM,
        IncidentStatus.DETECTED, "검증 매장", "검증 담당", now.isoformat(), now.isoformat(), tenant_id=tenant,
        evidence=[Evidence("e", "PII-SENTINEL", "TRANSACTION", "PII-SENTINEL 원문", .9)])
    incident = repo.save(incident)
    with persistence.transaction(tenant) as uow:
        uow.configs.append(ConfigVersion(1, tenant, RuntimeConfig(jev_enabled=True, auto_investigation=True), "Shadow 검증", "admin", now), 0)
    job = Job(str(uuid4()), tenant, "incident.snapshot", incident.id, now, now, incident_id=incident.id, store=incident.store)
    with psycopg.connect(dsn, autocommit=True) as connection:
        job = PostgresJobRepository(connection, tenant).save(job)
        worker = JobWorker(connection, snapshot_processor(repo, ShadowDecisions(persistence, clock=lambda: now)), clock=lambda: now, tenant_id=tenant)
        assert worker.run_once()
        assert PostgresJobRepository(connection, tenant).get(job.job_id).status == JobStatus.COMPLETED
    assert repo.get(incident.id) == incident
    # 재시작한 Application과 동시 재전달도 동일 Job/ruleset 감사 한 건만 남깁니다.
    def replay(_):
        return ShadowDecisions(AccessPersistence(PostgresIncidentRepository(dsn)), clock=lambda: now).record(job)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(replay, range(2)))
    assert records[0] == records[1]
    first = records[0]
    assert first.result.route == "TRANSACTION_INVESTIGATION" and first.result.config_version == 1
    assert not first.result.requires_llm and first.result.mode == "SHADOW"

    def http(token="reader", latest=False):
        app = create_app(PostgresIncidentRepository(dsn), identity_provider=provider)
        return TestClient(app).get(f"/api/v1/incidents/{incident.id}/decisions" + ("/latest" if latest else ""), headers={"Authorization": "Bearer "+token})
    assert http().status_code == 200 and len(http().json()["decisions"]) == 1
    assert http(latest=True).json()["decision_id"] == first.decision_id
    assert http("other").status_code == 404 and http("store").status_code == 403
    assert "input_digest" not in http().text and "PII-SENTINEL" not in http().text
    # 실패 원문은 버리고 안정적인 실패 감사만 남기며 Incident를 변경하지 않습니다.
    failed_job = replace(job, job_id=str(uuid4()), version=0)
    with psycopg.connect(dsn, autocommit=True) as connection:
        PostgresJobRepository(connection, tenant).save(failed_job)
    engine = Mock()
    engine.evaluate.side_effect = RuntimeError("PII-SENTINEL credential")
    failed = ShadowDecisions(persistence, engine=engine, clock=lambda: now).record(failed_job)
    assert failed.error_code == "DECISION_INTERNAL_ERROR" and not failed.result.investigation_agents
    assert repo.get(incident.id) == incident
    with psycopg.connect(dsn, autocommit=True) as connection:
        documents = connection.execute("SELECT document FROM serviq_decisions WHERE tenant_id=%s", (tenant,)).fetchall()
        assert len(documents) == 2 and "PII-SENTINEL" not in str(documents)
        audits = connection.execute("SELECT document FROM serviq_audit WHERE tenant_id=%s", (tenant,)).fetchall()
        assert len(audits) == 2 and {a[0]["result"] for a in audits} == {"SUCCESS", "FAILED"}
        assert all(a[0]["principal_id"] == "job-worker" and a[0]["resource_type"] == "decision" for a in audits)
        assert "PII-SENTINEL" not in str(audits)
        for verb in ("UPDATE serviq_decisions SET mode='SHADOW'", "DELETE FROM serviq_decisions"):
            try:
                with connection.transaction():
                    connection.execute(verb+" WHERE tenant_id=%s", (tenant,))
            except psycopg.errors.RaiseException:
                pass
            else:
                raise AssertionError("과거 판단 기록의 수정·삭제가 금지되어야 합니다.")
        # 감사 INSERT 실패는 Decision INSERT도 롤백하며 Job 업무 상태와 분리됩니다.
        atomic_job = replace(job, job_id=str(uuid4()), version=0)
        PostgresJobRepository(connection, tenant).save(atomic_job)
        constraint = "jev_smoke_"+uuid4().hex
        connection.execute(sql.SQL("ALTER TABLE serviq_audit ADD CONSTRAINT {} CHECK (NOT (tenant_id={} AND document->>'request_id'={})) NOT VALID").format(sql.Identifier(constraint), sql.Literal(tenant), sql.Literal(atomic_job.job_id)))
        try:
            assert ShadowDecisions(persistence, clock=lambda: now).record(atomic_job) is None
            assert connection.execute("SELECT count(*) FROM serviq_decisions WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 2
            assert connection.execute("SELECT count(*) FROM serviq_audit WHERE tenant_id=%s", (tenant,)).fetchone()[0] == 2
            assert PostgresJobRepository(connection, tenant).get(atomic_job.job_id).status == JobStatus.PENDING
        finally:
            connection.execute(sql.SQL("ALTER TABLE serviq_audit DROP CONSTRAINT {}").format(sql.Identifier(constraint)))
    print("[통과] Jev PostgreSQL Worker Shadow·재시작/동시 중복·Config lineage·append-only·Tenant/store·PII 미노출·실패 격리")


def main():
    dsn = os.environ.get("SERVIQ_TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("전용 테스트 DB의 SERVIQ_TEST_DATABASE_URL을 명시해 주세요.")
    verify(dsn)


if __name__ == "__main__":
    main()
