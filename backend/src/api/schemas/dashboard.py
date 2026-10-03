"""Dashboard의 읽기 전용 응답을 명시합니다."""
from typing import Literal

from pydantic import BaseModel, Field


class DashboardKpisResponse(BaseModel):
    open_incidents: int = Field(ge=0)
    critical_incidents: int = Field(ge=0)
    pending_approvals: int = Field(ge=0)
    failed_jobs: int = Field(ge=0)
    dlq_jobs: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    running_jobs: int = Field(ge=0)


class TrendResponse(BaseModel):
    day: str
    detected: int = Field(ge=0)
    resolved: int = Field(ge=0)


class CauseResponse(BaseModel):
    label: str
    count: int = Field(ge=0)


class CapaResponse(BaseModel):
    status: Literal["PROPOSED", "APPROVED", "EXECUTED"]
    count: int = Field(ge=0)


class IntegrationAvailability(BaseModel):
    status: Literal["NOT_IMPLEMENTED"]
    reason: str


class PriorityIncidentResponse(BaseModel):
    id: str
    title: str
    store: str
    owner: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class DashboardResponse(BaseModel):
    as_of: str
    window: Literal["7d"]
    timezone: Literal["UTC"]
    kpis: DashboardKpisResponse
    incident_trend: list[TrendResponse]
    root_cause_distribution: list[CauseResponse]
    capa_status: list[CapaResponse]
    integration_health: IntegrationAvailability
    priority_incidents: list[PriorityIncidentResponse]
