"""프론트엔드와 의미를 맞춘 독립적인 HTTP 계약입니다."""

from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from src.domain.incidents.enums import (
    ActionStatus,
    EvidenceStatus,
    IncidentStatus,
    Priority,
    Severity,
    VerificationResult,
)

NonEmpty = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Identifier = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CommandRequest(InputModel):
    expected_version: int | None = Field(default=None, ge=1)


class CreateIncidentRequest(InputModel):
    title: NonEmpty
    severity: Severity
    store: Identifier
    owner: Identifier
    sla_due_at: AwareDatetime | None = None
    priority: Priority = Priority.P2


class TriageRequest(CommandRequest):
    severity: Severity | None = None
    occurred_at: AwareDatetime | None = None


class EvidenceInput(InputModel):
    id: Identifier
    source: NonEmpty
    type: Identifier
    summary: NonEmpty
    confidence: float = Field(ge=0, le=1)
    status: EvidenceStatus = EvidenceStatus.AVAILABLE


class EvidenceRequest(CommandRequest):
    evidence: EvidenceInput


class RootCauseInput(InputModel):
    id: Identifier
    summary: NonEmpty
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[Identifier] = Field(min_length=1)
    counter_evidence_ids: list[Identifier] = Field(default_factory=list)


class RcaRequest(CommandRequest):
    candidates: list[RootCauseInput] = Field(min_length=1, max_length=30)


class CorrectiveActionInput(InputModel):
    id: Identifier
    summary: NonEmpty
    risk_level: Severity
    expected_effect: NonEmpty
    verification_criteria: NonEmpty


class ActionRequest(CommandRequest):
    actions: list[CorrectiveActionInput] = Field(min_length=1, max_length=30)


class VerificationRequest(CommandRequest):
    result: VerificationResult
    summary: NonEmpty


class ReopenRequest(CommandRequest):
    reason: NonEmpty


class EvidenceResponse(BaseModel):
    id: str
    source: str
    type: str
    summary: str
    confidence: float
    status: EvidenceStatus


class RootCauseResponse(BaseModel):
    id: str
    summary: str
    confidence: float
    supporting_evidence_ids: list[str]
    counter_evidence_ids: list[str]


class CorrectiveActionResponse(BaseModel):
    id: str
    summary: str
    risk_level: Severity
    expected_effect: str
    verification_criteria: str
    status: ActionStatus


class VerificationResponse(BaseModel):
    id: str
    result: VerificationResult
    summary: str
    verified_at: str | None = None
    execution_id: str | None = None
    evidence_refs: list[str] = []
    criteria: str | None = None
    observation_mode: Literal["SIMULATED"] | None = None


class TimelineResponse(BaseModel):
    status: IncidentStatus
    occurred_at: str
    reason: str | None = None


class IncidentResponse(BaseModel):
    id: str
    display_id: str
    title: str
    severity: Severity
    status: IncidentStatus
    store: str
    owner: str
    created_at: str
    sla_due_at: str
    timeline: list[TimelineResponse]
    evidence: list[EvidenceResponse]
    root_cause_candidates: list[RootCauseResponse]
    corrective_actions: list[CorrectiveActionResponse]
    verification: VerificationResponse | None = None
    approved: bool
    version: int
    priority: Priority


class ActionPermissionResponse(BaseModel):
    allowed: bool
    reason: str


class WorkspaceResponse(BaseModel):
    priority: Priority
    tasks: list[dict]
    actions: dict[str, ActionPermissionResponse]
    commands: dict[str, ActionPermissionResponse]
