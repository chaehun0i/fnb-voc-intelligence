"""Jev는 정규화된 사실과 불변 정책만 받으며 외부 실행을 하지 않습니다."""
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.domain.config.models import ResolvedConfig
from src.domain.incidents.enums import IncidentStatus, Priority, Severity


class DecisionRoute(StrEnum):
    COLD_CHAIN_INVESTIGATION = "COLD_CHAIN_INVESTIGATION"
    SUPPLIER_LOT_INVESTIGATION = "SUPPLIER_LOT_INVESTIGATION"
    HISTORY_RECURRENCE = "HISTORY_RECURRENCE"
    TRANSACTION_INVESTIGATION = "TRANSACTION_INVESTIGATION"
    GENERAL_INVESTIGATION = "GENERAL_INVESTIGATION"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RequestedMode(StrEnum):
    AUTO = "AUTO"
    ASSISTED = "ASSISTED"
    MANUAL = "MANUAL"


class AgentType(StrEnum):
    TEMPERATURE = "TEMPERATURE"
    INVENTORY = "INVENTORY"
    LOT = "LOT"
    SUPPLIER = "SUPPLIER"
    HISTORY = "HISTORY"
    TRANSACTION = "TRANSACTION"


class Category(StrEnum):
    COLD_CHAIN = "COLD_CHAIN"
    SUPPLIER_LOT = "SUPPLIER_LOT"
    TRANSACTION = "TRANSACTION"
    FOOD_SAFETY = "FOOD_SAFETY"
    GENERAL = "GENERAL"
    UNKNOWN = "UNKNOWN"
    RESTRICTED = "RESTRICTED"


class DecisionReasonCode(StrEnum):
    ENGINE_FAILURE = "ENGINE_FAILURE"
    CRITICAL_MANUAL_GATE = "CRITICAL_MANUAL_GATE"
    CATEGORY_BLOCKED = "CATEGORY_BLOCKED"
    AUTOMATION_DISABLED = "AUTOMATION_DISABLED"
    MANUAL_REQUESTED = "MANUAL_REQUESTED"
    STATUS_NOT_INVESTIGABLE = "STATUS_NOT_INVESTIGABLE"
    FOOD_SAFETY_RISK = "FOOD_SAFETY_RISK"
    RECURRENCE_RISK = "RECURRENCE_RISK"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"
    NO_ALLOWED_AGENTS = "NO_ALLOWED_AGENTS"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    PARALLELISM_LIMIT = "PARALLELISM_LIMIT"
    PROVIDER_POLICY_DENIED = "PROVIDER_POLICY_DENIED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


@dataclass(frozen=True)
class DecisionContext:
    tenant_id: str
    incident_id: str
    incident_status: IncidentStatus
    severity: Severity
    priority: Priority
    category: Category
    store_id: str
    known_evidence_types: tuple[AgentType, ...]
    data_availability: tuple[AgentType, ...]
    recurrence_hint: bool
    requested_mode: RequestedMode
    policy: ResolvedConfig
    config_version: int
    occurred_at: datetime

    def __post_init__(self):
        for key in ("known_evidence_types", "data_availability"):
            object.__setattr__(self, key, tuple(getattr(self, key)))


@dataclass(frozen=True)
class DecisionResult:
    route: DecisionRoute
    risk_level: Severity
    priority: Priority
    investigation_agents: tuple[AgentType, ...]
    requires_llm: bool
    requires_human_review: bool
    workflow_profile: str
    budget_profile: str
    manual_reason: str | None
    reason_codes: tuple[DecisionReasonCode, ...]
    config_version: int
    ruleset_version: str = "1"
    mode: str = "SHADOW"


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    tenant_id: str
    incident_id: str
    source_job_id: str
    result: DecisionResult
    input_digest: str
    decided_at: datetime
    duration_ms: float
    incident_version: int
    error_code: str | None = None


class DecisionValidationError(Exception):
    """미확인 분류는 fallback이며 잘못된 타입·정책 입력은 오류입니다."""
