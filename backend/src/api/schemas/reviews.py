"""Review 화면이 필요로 하는 승인 원본의 읽기 계약입니다."""
from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas.incidents import EvidenceResponse, InputModel, NonEmpty
from src.domain.incidents.enums import Severity


class ActionPermission(BaseModel):
    allowed: bool
    reason: str


class ReviewApprovalResponse(BaseModel):
    id: str
    incident_id: str
    type: str
    risk_level: Severity
    requester: str
    requested_at: str
    evidence_completeness: int
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    version: int
    actions: dict[str, ActionPermission]


class ReviewHistory(BaseModel):
    occurred_at: str
    actor: str
    summary: str


class ReviewDetailResponse(BaseModel):
    approval_id: str
    incident_display_id: str
    incident_title: str
    proposed_action: str
    expected_effect: str
    verification_criteria: str
    due_at: str
    evidence: list[EvidenceResponse]
    history: list[ReviewHistory]


class ReviewResponse(BaseModel):
    approval: ReviewApprovalResponse
    detail: ReviewDetailResponse


class ReviewDecisionRequest(InputModel):
    expected_version: int = Field(ge=1)
    reason: NonEmpty
