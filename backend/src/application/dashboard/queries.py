"""인증된 범위와 단일 기준 시각을 Projection에 전달합니다."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from src.application.dashboard.models import DashboardProjection, InvalidDashboardWindow
from src.application.security.authorization import require
from src.application.security.principal import Principal, Role


def store_scope(principal: Principal) -> list[str] | None:
    """빈 STORE_MANAGER 범위는 전체 매장 권한으로 확대하지 않습니다."""
    if principal.store_scope or (Role.STORE_MANAGER in principal.roles and Role.HQ_ADMIN not in principal.roles):
        return sorted(principal.store_scope)
    return None


class DashboardQueries:
    def __init__(self, projection: DashboardProjection, clock: Callable[[], datetime] | None = None):
        self.projection = projection
        self.clock = clock or (lambda: datetime.now(UTC))

    def get(self, principal: Principal, window: str = "7d"):
        require(principal, "read")
        if window != "7d":
            raise InvalidDashboardWindow()
        as_of = self.clock()
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("집계 시각에는 시간대가 필요합니다.")
        as_of = as_of.astimezone(UTC)
        start = as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
        return self.projection.project(principal, as_of, start)
