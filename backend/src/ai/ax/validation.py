"""User tasks are observations, never a second Incident state machine."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.ai.ax.models import SafeModel

Scenario = Literal["happy_path", "more_evidence", "reopen", "manual_takeover", "abandon"]
SessionStatus = Literal["ACTIVE", "COMPLETED", "ABANDONED"]


def validate_synthetic_database_name(name):
    if name == "fnb_voc" or not any(marker in name.lower() for marker in ("test", "validation", "_ci", "ci_")):
        raise ValueError("USER_VALIDATION_REQUIRES_EXPLICIT_TEST_DATABASE")


class ValidationTask(SafeModel):
    task_id: Literal["incident-understanding"] = "incident-understanding"
    task_version: Literal["1"] = "1"
    business_goal: str = "이 사건의 가장 가능성 높은 원인과 다음 조치를 판단하고 최종 상태를 확인해 주세요."
    success_criteria: tuple[str, ...] = (
        "확보한 근거와 부족한 근거를 검토한다.",
        "필요한 사람 판단을 실제 업무 명령으로 제출한다.",
        "검증 결과와 최종 사건 상태를 확인하고 의견을 남긴다.",
    )
    expected_entry: Literal["FIRST_RUN"] = "FIRST_RUN"
    expected_terminal_state: Literal["RESOLVED", "REOPENED", "MORE_EVIDENCE_REQUIRED", "MANUAL_TAKEOVER", "ABANDONED"]
    max_expected_steps: int | None = Field(default=None, ge=1, le=100)


def validation_task(scenario: Scenario) -> ValidationTask:
    terminal = {"happy_path": "RESOLVED", "more_evidence": "MORE_EVIDENCE_REQUIRED",
        "reopen": "REOPENED", "manual_takeover": "MANUAL_TAKEOVER", "abandon": "ABANDONED"}
    return ValidationTask(expected_terminal_state=terminal[scenario])


class ValidationSession(SafeModel):
    session_id: UUID
    tenant_id: str = Field(min_length=1, max_length=128)
    store_id: str = Field(min_length=1, max_length=128)
    scenario_id: Scenario
    participant_ref: UUID  # pseudonymous, server generated; not a name/email/token
    task_version: Literal["1"] = "1"
    entry_point: Literal["FIRST_RUN", "INCIDENT"] = "FIRST_RUN"
    incident_id: str | None = Field(default=None, max_length=128)
    agent_run_id: str | None = Field(default=None, max_length=128)
    release_candidate_id: str | None = Field(default=None, max_length=128)
    status: SessionStatus = "ACTIVE"
    started_at: datetime
    completed_at: datetime | None = None
    consent_scope: Literal["TASK_EVENTS_ONLY"] = "TASK_EVENTS_ONLY"
    created_at: datetime
    validation_kind: Literal["SYNTHETIC", "USER_OBSERVATION"]
    completed_phase: Literal["RESOLVED", "REOPENED", "VERIFYING", "INVESTIGATING", "PENDING_APPROVAL", "ACTION_PROPOSED", "RCA_READY"] | None = None

    @model_validator(mode="after")
    def coherent(self):
        times = [self.started_at, self.created_at, self.completed_at]
        if any(t is not None and t.utcoffset() is None for t in times):
            raise ValueError("VALIDATION_TIMESTAMP_TIMEZONE_REQUIRED")
        if (self.status == "ACTIVE") != (self.completed_at is None):
            raise ValueError("VALIDATION_TERMINAL_TIMESTAMP_REQUIRED")
        if self.completed_at and self.completed_at < self.started_at:
            raise ValueError("VALIDATION_TIMESTAMP_ORDER")
        if self.completed_phase and self.status != "COMPLETED":
            raise ValueError("VALIDATION_COMPLETION_RECEIPT_REQUIRED")
        return self


Milestone = Literal["ONBOARDING_STARTED", "DATA_READY", "INCIDENT_OPENED", "AI_BRIEF_VIEWED",
    "EVIDENCE_REVIEWED", "HUMAN_ACTION_PRESENTED", "REVIEW_OPENED", "DECISION_SUBMITTED",
    "VERIFICATION_VIEWED", "FINAL_STATUS_VIEWED", "FEEDBACK_SUBMITTED"]


class JourneyMilestone(SafeModel):
    milestone: Milestone
    occurred_at: datetime


class ValidationJourney(SafeModel):
    session_id: UUID
    milestones: tuple[JourneyMilestone, ...]
    incident_status: str | None
    task_success: bool
    status: SessionStatus


class ValidationMetric(SafeModel):
    name: Literal["task_completion_rate", "time_to_first_useful_evidence", "time_to_human_action",
        "time_to_decision", "human_intervention_rate", "accept_rate", "edit_rate", "reject_rate",
        "request_more_evidence_rate", "manual_takeover_rate", "loop_abort_rate",
        "end_to_end_completion_rate", "median_task_duration", "cost_per_completed_incident"]
    value: float | None = Field(default=None, ge=0)
    sample_size: int = Field(ge=0, le=100)
    availability: Literal["AVAILABLE", "PARTIAL", "INSUFFICIENT_SAMPLE", "UNAVAILABLE"]
    unit: Literal["ratio", "seconds", "estimated_usd"]
    window: Literal["7d"] = "7d"


def project_journey(session, events, ax=None, decision_at=None):
    """Order-independent unique milestones; page views alone never mean success.

    The application supplies authorized canonical AX and actual Approval time.
    Client DECISION_SUBMITTED is deliberately ignored without that receipt.
    """
    observed = {}
    for event in events:
        if event.session_id != session.session_id or event.tenant_id != session.tenant_id:
            raise ValueError("VALIDATION_EVENT_SCOPE")
        if event.milestone and event.occurred_at >= session.started_at and (event.milestone != "FEEDBACK_SUBMITTED" or event.feedback_decision and event.feedback_stage == "RAW"):
            previous = observed.get(event.milestone)
            observed[event.milestone] = min(previous, event.occurred_at) if previous else event.occurred_at
    observed.pop("DECISION_SUBMITTED", None)
    if decision_at and decision_at >= session.started_at:
        observed["DECISION_SUBMITTED"] = decision_at
    if session.status != "COMPLETED" and (ax is None or ax.source_run_id is None):
        for name in ("AI_BRIEF_VIEWED", "EVIDENCE_REVIEWED", "HUMAN_ACTION_PRESENTED", "VERIFICATION_VIEWED"):
            observed.pop(name, None)
    elif session.status != "COMPLETED" and not ax.coverage.evidence_count:
        observed.pop("EVIDENCE_REVIEWED", None)
    if session.status != "COMPLETED" and (ax is None or ax.verification_result is None):
        observed.pop("VERIFICATION_VIEWED", None)
    if session.status != "COMPLETED" and (ax is None or ax.current_phase not in {"RESOLVED", "REOPENED", "VERIFYING"}):
        observed.pop("FINAL_STATUS_VIEWED", None)
    required = {"AI_BRIEF_VIEWED", "FEEDBACK_SUBMITTED"}
    if session.scenario_id in {"happy_path", "reopen"}:
        required |= {"EVIDENCE_REVIEWED", "DECISION_SUBMITTED", "VERIFICATION_VIEWED", "FINAL_STATUS_VIEWED"}
        outcome = bool(ax and ax.current_phase == validation_task(session.scenario_id).expected_terminal_state
            and ax.verification_result == ("PASS" if session.scenario_id == "happy_path" else "FAIL"))
    elif session.scenario_id == "more_evidence":
        outcome = bool(ax and ax.human_action == "MORE_EVIDENCE_REQUIRED"
            and any(e.feedback_decision == "REQUEST_MORE_EVIDENCE" for e in events))
    elif session.scenario_id == "manual_takeover":
        outcome = bool(ax and ax.runtime and ax.runtime.control_status == "MANUAL_TAKEOVER")
    else:
        outcome = False  # abandonment is a measured non-completion, not task success
    # COMPLETED is a server-issued task receipt; later Incident changes do not revoke history.
    success = bool(session.status == "COMPLETED" and session.completed_phase) or session.status != "ABANDONED" and outcome and required <= observed.keys()
    return ValidationJourney(session_id=session.session_id,
        milestones=tuple(JourneyMilestone(milestone=name, occurred_at=at) for name, at in sorted(observed.items())),
        incident_status=session.completed_phase or (ax.current_phase if ax else None), task_success=bool(success), status=session.status)
