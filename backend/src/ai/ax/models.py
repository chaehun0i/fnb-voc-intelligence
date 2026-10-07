"""SDK-independent user task projection, not a second Incident/Agent aggregate."""
from datetime import datetime
from typing import Literal

from pydantic import Field

from src.ai.models import SafeModel

HumanAction = Literal["NONE", "REVIEW_REQUIRED", "APPROVAL_REQUIRED", "MORE_EVIDENCE_REQUIRED",
    "MANUAL_TAKEOVER_RECOMMENDED", "POLICY_BLOCKED", "BUDGET_INCREASE_REQUIRED", "VERIFICATION_REQUIRED"]
ActionType = Literal["NONE", "OPEN_REVIEW", "COLLECT_EVIDENCE", "MANUAL_REVIEW", "CHECK_RESULT", "VERIFY", "OPEN_WORKSPACE"]
Dimension = Literal["HISTORY", "TRANSACTION", "INVENTORY"]


class AIBrief(SafeModel):
    headline: str = Field(max_length=160)
    summary: str = Field(max_length=600)
    primary_hypothesis: str | None = Field(default=None, max_length=256)
    confidence_level: Literal["LOW", "MEDIUM", "INCONCLUSIVE"] = "INCONCLUSIVE"


class EvidenceCoverage(SafeModel):
    confirmed: tuple[Dimension, ...] = ()
    missing: tuple[Dimension, ...] = ()
    conflicting: tuple[Dimension, ...] = ()
    stale: tuple[Dimension, ...] = ()
    evidence_count: int = Field(default=0, ge=0, le=20)


class NextBestAction(SafeModel):
    action_type: ActionType = "NONE"
    label: str = "현재 업무 상태를 확인해 주세요."
    reason: str = "아직 자동 조사 결과가 없습니다."
    risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    permission: bool = False
    requires_approval: bool = False
    blocking_reason: str | None = None
    alternative_actions: tuple[ActionType, ...] = ()


class AgentProgress(SafeModel):
    agent_type: Dimension
    label: str
    status: Literal["RUNNING", "SUCCESS", "FAILED", "UNAVAILABLE", "NO_EVIDENCE", "STALE"]
    evidence_count: int = Field(ge=0, le=20)


class Explanation(SafeModel):
    supporting_refs: tuple[str, ...] = ()
    contradicting_refs: tuple[str, ...] = ()
    missing_codes: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    cannot_verify: tuple[str, ...] = ()
    technical_trace_available: bool = False


class IncidentAX(SafeModel):
    schema_version: Literal["incident-ax-1"] = "incident-ax-1"
    incident_id: str
    current_phase: str
    brief: AIBrief
    coverage: EvidenceCoverage = EvidenceCoverage()
    uncertainties: tuple[str, ...] = ()
    human_action: HumanAction = "NONE"
    next_action: NextBestAction
    progress: tuple[AgentProgress, ...] = ()
    verification_result: Literal["PASS", "FAIL", "INCONCLUSIVE"] | None = None
    execution_mode: Literal["INTERNAL_RECORD_ONLY"] | None = None
    approval_status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None
    source_run_id: str | None = None
    manifest_reference: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    decision_reference: str | None = None
    explanation: Explanation = Explanation()
    updated_at: datetime
