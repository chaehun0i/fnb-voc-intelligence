"""RCA에 없는 범주를 만들지 않고 실제 후보와 조치를 집계합니다."""
from dataclasses import replace
from datetime import UTC, datetime

from src.application.dashboard.queries import DashboardQueries
from src.application.security.principal import Principal, Role
from src.domain.incidents.models import RootCauseCandidate
from src.infrastructure.dashboard_projection import MemoryDashboardProjection
from tests.test_review_queries import review_app


def test_rca_unclassified_capa_and_empty():
    app = review_app()
    repo = app.state.access_persistence.incidents
    item = repo.get("review-incident")
    repo.save(replace(item, root_cause_candidates=[RootCauseCandidate("cause", "원인 가설", 0.8)],
                      corrective_actions=[replace(item.corrective_actions[0], id=status, status=status)
                                          for status in ["PROPOSED", "APPROVED", "EXECUTED"]]))
    query = DashboardQueries(MemoryDashboardProjection(app.state.access_persistence), lambda: datetime(2026, 10, 3, tzinfo=UTC))
    result = query.get(Principal("r", "legacy-local", frozenset({Role.AUDITOR})))
    assert [(c.label, c.count) for c in result.root_cause_distribution] == [("미분류", 1)]
    assert [(c.status, c.count) for c in result.capa_status] == [("PROPOSED", 1), ("APPROVED", 1), ("EXECUTED", 1)]
    empty = query.get(Principal("r", "empty", frozenset({Role.AUDITOR})))
    assert empty.root_cause_distribution == []
    assert [c.count for c in empty.capa_status] == [0, 0, 0]
