"""승인과 Job의 원본 상태를 집계하고 조회 자체는 저장하지 않습니다."""
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime

from src.application.dashboard.queries import DashboardQueries
from src.application.security.principal import Principal, Role
from src.domain.jobs.models import Job
from src.infrastructure.dashboard_projection import MemoryDashboardProjection
from tests.test_review_queries import review_app


def test_approval_and_job_counts_no_mutation():
    app = review_app()
    persistence = app.state.access_persistence
    now = datetime(2026, 10, 3, tzinfo=UTC)
    with persistence.transaction("legacy-local") as uow:
        for status in ["PENDING", "FAILED", "DLQ", "COMPLETED", "CANCELLED", "RUNNING"]:
            job = Job(status, "legacy-local", "snapshot", "correlation", now, now, store="강남점")
            uow.jobs.save(replace(job, status=status, worker_id="worker" if status == "RUNNING" else None,
                lease_until=now.replace(hour=1) if status == "RUNNING" else None))
        uow.jobs.save(Job("other", "legacy-local", "snapshot", "corr", now, now, store="다른점"))
    incident = persistence.incidents.get("review-incident")
    persistence.incidents.save(replace(incident, store="강남점"))
    before = deepcopy(persistence.memory.data)
    query = DashboardQueries(MemoryDashboardProjection(persistence), lambda: now)
    result = query.get(Principal("r", "legacy-local", frozenset({Role.AUDITOR}), frozenset({"강남점"})))
    assert result.kpis.pending_approvals == 1
    assert (result.kpis.failed_jobs, result.kpis.dlq_jobs, result.kpis.queue_depth, result.kpis.running_jobs) == (1, 1, 1, 1)
    assert persistence.memory.data == before
    empty = query.get(Principal("r", "other-tenant", frozenset({Role.AUDITOR})))
    assert empty.kpis.queue_depth == empty.kpis.pending_approvals == 0
