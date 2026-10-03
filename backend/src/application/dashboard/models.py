"""HTTP와 저장 기술에 독립적인 Dashboard read contract입니다."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from src.application.security.principal import Principal


@dataclass(frozen=True)
class DashboardKpis:
    open_incidents: int = 0
    critical_incidents: int = 0
    pending_approvals: int = 0
    failed_jobs: int = 0
    dlq_jobs: int = 0
    queue_depth: int = 0
    running_jobs: int = 0


@dataclass(frozen=True)
class TrendBucket:
    day: str
    detected: int = 0
    resolved: int = 0


@dataclass(frozen=True)
class CauseCount:
    label: str
    count: int


@dataclass(frozen=True)
class CapaCount:
    status: str
    count: int


@dataclass(frozen=True)
class PriorityIncident:
    id: str
    title: str
    store: str
    owner: str
    severity: str


@dataclass(frozen=True)
class DashboardSnapshot:
    as_of: str
    incident_trend: list[TrendBucket]
    kpis: DashboardKpis = field(default_factory=DashboardKpis)
    window: str = "7d"
    timezone: str = "UTC"
    root_cause_distribution: list[CauseCount] = field(default_factory=list)
    capa_status: list[CapaCount] = field(default_factory=list)
    priority_incidents: list[PriorityIncident] = field(default_factory=list)
    integration_health: dict[str, str] = field(default_factory=lambda: {
        "status": "NOT_IMPLEMENTED", "reason": "실제 연동 상태 집계는 준비 중입니다.",
    })


class DashboardProjection(Protocol):
    def project(self, principal: Principal, as_of: datetime, start: datetime) -> DashboardSnapshot: ...


class DashboardUnavailable(Exception):
    """내부 DB 정보 없이 집계 실패를 알립니다."""


class InvalidDashboardWindow(ValueError):
    """지원하지 않는 기간입니다."""
