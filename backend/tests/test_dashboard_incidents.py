"""상태·UTC 날짜 경계·매장 범위는 결정적입니다."""
from dataclasses import replace
from datetime import UTC, datetime

from src.application.dashboard.queries import DashboardQueries
from src.application.security.principal import Principal, Role
from src.domain.incidents.models import StateTransition
from src.infrastructure.dashboard_projection import MemoryDashboardProjection
from tests.test_review_queries import review_app


def test_incident_kpis_and_utc_buckets():
    app = review_app()
    repo = app.state.access_persistence.incidents
    base = repo.get("review-incident")
    for id, state, created in [("open", "REOPENED", "2026-09-27T09:00:00+09:00"),
                               ("closed", "CLOSED", "2026-09-26T23:59:59Z"),
                               ("other", "DETECTED", "2026-10-03T00:00:00Z")]:
        repo.save(replace(base, id=id, version=0, status=state, severity="CRITICAL", created_at=created,
                          store="hidden" if id == "other" else "visible",
                          timeline=[StateTransition("RESOLVED", "2026-10-02T10:00:00Z")] if id == "closed" else []))
    principal = Principal("r", "legacy-local", frozenset({Role.AUDITOR}), frozenset({"visible"}))
    result = DashboardQueries(MemoryDashboardProjection(app.state.access_persistence),
                              lambda: datetime(2026, 10, 3, tzinfo=UTC)).get(principal)
    assert result.kpis.open_incidents == result.kpis.critical_incidents == 1
    assert len(result.incident_trend) == 7
    assert result.incident_trend[0].detected == 1
    assert result.incident_trend[-2].resolved == 1
    assert sum(t.detected for t in result.incident_trend) == 1
