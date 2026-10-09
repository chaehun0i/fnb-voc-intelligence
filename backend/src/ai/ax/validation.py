"""User tasks are observations, never a second Incident state machine."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from src.ai.ax.models import SafeModel

Scenario = Literal["happy_path", "more_evidence", "reopen", "manual_takeover", "abandon"]
SessionStatus = Literal["ACTIVE", "COMPLETED", "ABANDONED"]


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
    expected_terminal_state: Literal["RESOLVED", "REOPENED", "VERIFYING", "MANUAL_TAKEOVER", "ABANDONED"]
    max_expected_steps: int | None = Field(default=None, ge=1, le=100)


def validation_task(scenario: Scenario) -> ValidationTask:
    terminal = {"happy_path": "RESOLVED", "more_evidence": "VERIFYING",
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

    @model_validator(mode="after")
    def coherent(self):
        times = [self.started_at, self.created_at, self.completed_at]
        if any(t is not None and t.utcoffset() is None for t in times):
            raise ValueError("VALIDATION_TIMESTAMP_TIMEZONE_REQUIRED")
        if (self.status == "ACTIVE") != (self.completed_at is None):
            raise ValueError("VALIDATION_TERMINAL_TIMESTAMP_REQUIRED")
        if self.completed_at and self.completed_at < self.started_at:
            raise ValueError("VALIDATION_TIMESTAMP_ORDER")
        return self
