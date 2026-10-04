"""HTTP 응답 DTO는 Decision Domain과 독립적으로 정의합니다."""
from typing import Literal

from pydantic import BaseModel


class DecisionResponse(BaseModel):
    decision_id: str
    incident_id: str
    source_job_id: str
    mode: Literal["SHADOW"]
    route: Literal["COLD_CHAIN_INVESTIGATION", "SUPPLIER_LOT_INVESTIGATION", "HISTORY_RECURRENCE", "TRANSACTION_INVESTIGATION", "GENERAL_INVESTIGATION", "MANUAL_REVIEW"]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    priority: Literal["P1", "P2", "P3"]
    investigation_agents: list[Literal["TEMPERATURE", "INVENTORY", "LOT", "SUPPLIER", "HISTORY", "TRANSACTION"]]
    requires_llm: bool
    requires_human_review: bool
    workflow_profile: str
    budget_profile: str
    manual_reason: str | None
    reason_codes: list[str]
    config_version: int
    ruleset_version: str
    decided_at: str
    duration_ms: float
    incident_version: int
    error_code: str | None


class DecisionHistoryResponse(BaseModel):
    decisions: list[DecisionResponse]
    limit: int
    offset: int
    has_more: bool
