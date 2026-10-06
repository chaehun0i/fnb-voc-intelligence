"""HTTP나 저장 기술에 의존하지 않는 인시던트 모델입니다."""

from dataclasses import dataclass, field

from .enums import (
    ActionStatus,
    EvidenceStatus,
    IncidentStatus,
    Priority,
    Severity,
    VerificationResult,
)


@dataclass(frozen=True)
class Evidence:
    id: str
    source: str
    type: str
    summary: str
    confidence: float
    status: EvidenceStatus = EvidenceStatus.AVAILABLE

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", EvidenceStatus(self.status))
        if not 0 <= self.confidence <= 1:
            raise ValueError("증거 신뢰도는 0과 1 사이여야 합니다.")


@dataclass(frozen=True)
class RootCauseCandidate:
    id: str
    summary: str
    confidence: float
    supporting_evidence_ids: list[str] = field(default_factory=list)
    counter_evidence_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("원인 후보 신뢰도는 0과 1 사이여야 합니다.")


@dataclass(frozen=True)
class CorrectiveAction:
    id: str
    summary: str
    risk_level: Severity
    expected_effect: str
    verification_criteria: str
    status: ActionStatus = ActionStatus.PROPOSED
    action_type: str | None = None
    target_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk_level", Severity(self.risk_level))
        object.__setattr__(self, "status", ActionStatus(self.status))


@dataclass(frozen=True)
class Verification:
    result: VerificationResult
    summary: str
    id: str = ""
    verified_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "result", VerificationResult(self.result))


@dataclass(frozen=True)
class StateTransition:
    status: IncidentStatus
    occurred_at: str
    reason: str | None = None


@dataclass(frozen=True)
class Incident:
    id: str
    display_id: str
    title: str
    severity: Severity
    status: IncidentStatus
    store: str
    owner: str
    created_at: str
    sla_due_at: str
    evidence: list[Evidence] = field(default_factory=list)
    root_cause_candidates: list[RootCauseCandidate] = field(default_factory=list)
    corrective_actions: list[CorrectiveAction] = field(default_factory=list)
    verification: Verification | None = None
    timeline: list[StateTransition] = field(default_factory=list)
    approved: bool = False
    version: int = 0
    priority: Priority = Priority.P2
    tenant_id: str = "legacy-local"

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", Severity(self.severity))
        object.__setattr__(self, "status", IncidentStatus(self.status))
        object.__setattr__(self, "priority", Priority(self.priority))
        if self.version < 0:
            raise ValueError("인시던트 버전은 음수일 수 없습니다.")
