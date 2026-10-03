"""Query는 단일 UTC 시각과 인증 범위를 전달하며 업무를 변경하지 않습니다."""
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src.application.dashboard.models import InvalidDashboardWindow
from src.application.dashboard.queries import DashboardQueries, store_scope
from src.application.security.principal import AccessError, Principal, Role


def test_dashboard_clock_window_and_scope():
    projection = Mock()
    principal = Principal("reader", "tenant-a", frozenset({Role.AUDITOR}))
    clock = Mock(return_value=datetime(2026, 10, 3, 9, tzinfo=timezone(timedelta(hours=9))))
    DashboardQueries(projection, clock).get(principal)
    projection.project.assert_called_once_with(principal, datetime(2026, 10, 3, tzinfo=UTC), datetime(2026, 9, 27, tzinfo=UTC))
    clock.assert_called_once()
    with pytest.raises(InvalidDashboardWindow):
        DashboardQueries(projection).get(principal, "365d")
    with pytest.raises(AccessError):
        DashboardQueries(projection).get(Principal("none", "tenant-a", frozenset()))
    assert store_scope(Principal("store", "a", frozenset({Role.STORE_MANAGER}))) == []
    assert store_scope(principal) is None


def test_dashboard_rejects_naive_clock():
    with pytest.raises(ValueError):
        DashboardQueries(Mock(), lambda: datetime(2026, 10, 3, tzinfo=UTC).replace(tzinfo=None)).get(Principal("r", "a", frozenset({Role.AUDITOR})))
