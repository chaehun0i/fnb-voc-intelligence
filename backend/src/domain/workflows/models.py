"""원문 대신 참조와 정규화 결과를 보관하는 SDK 독립 실행 계약입니다."""
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorkflowStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SafeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @field_validator("evidence_refs", check_fields=False)
    @classmethod
    def safe_refs(cls, values):
        import re
        if any(not re.fullmatch(r"review:[A-Za-z0-9_.:-]{1,128}", value) for value in values):
            raise ValueError("원문 대신 안전한 Review 출처 참조를 사용해 주세요.")
        return values


class EvidenceCandidate(SafeModel):
    source_ref: str = Field(pattern=r"^review:[A-Za-z0-9_.:-]{1,128}$")
    source_type: Literal["VOC_REVIEW"] = "VOC_REVIEW"
    rank: int = Field(ge=1, le=20)
    retrieved_at: datetime

    @field_validator("retrieved_at")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("검색 시각에 시간대를 포함해 주세요.")
        return value


class Finding(SafeModel):
    code: Literal["RELATED_HISTORY_FOUND"] = "RELATED_HISTORY_FOUND"
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=20)


class EvidenceGap(SafeModel):
    code: Literal["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE"]


class WorkflowState(SafeModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(min_length=1, max_length=128)
    workflow_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    agent_run_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    objective: Literal["HISTORY_INVESTIGATION"] = "HISTORY_INVESTIGATION"
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    route: str = Field(pattern=r"^[A-Z_]{1,64}$")
    evidence_refs: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    evidence_candidates: tuple[EvidenceCandidate, ...] = ()
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    errors: tuple[Literal["WORKFLOW_FAILED"], ...] = ()
    iteration: int = Field(default=0, ge=0, le=20)
    tool_call_count: int = Field(default=0, ge=0, le=50)
    token_spent: int = Field(default=0, ge=0)
    cost_spent: float = Field(default=0, ge=0)
    config_version: int = Field(ge=1)
    status: WorkflowStatus = WorkflowStatus.RUNNING


class AgentRun(SafeModel):
    agent_run_id: str
    tenant_id: str
    incident_id: str
    workflow_id: str
    job_id: str
    correlation_id: str
    config_version: int = Field(ge=1)
    jev_decision_id: str
    workflow_version: Literal["history-v1"] = "history-v1"
    status: WorkflowStatus = WorkflowStatus.RUNNING
    started_at: datetime
    completed_at: datetime | None = None
    error_code: Literal["WORKFLOW_FAILED"] | None = None
    safe_error_summary: Literal["조사를 완료하지 못했습니다. 작업 이력을 확인해 주세요."] | None = None
    state: WorkflowState

    @model_validator(mode="after")
    def lineage(self):
        if any(getattr(self, key) != getattr(self.state, key)
               for key in ("tenant_id", "incident_id", "workflow_id", "agent_run_id", "config_version")):
            raise ValueError("실행과 상태의 원본 참조가 일치해야 합니다.")
        if self.status == WorkflowStatus.COMPLETED and (
                self.completed_at is None or self.state.status != WorkflowStatus.COMPLETED):
            raise ValueError("Graph 저장 완료 전 실행을 완료할 수 없습니다.")
        return self

    @field_validator("started_at", "completed_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("실행 시각에 시간대를 포함해 주세요.")
        return value


class AgentStep(SafeModel):
    agent_run_id: str
    sequence: int = Field(ge=1, le=3)
    node_name: Literal["validate_context", "history_investigation", "persist_result"]
    attempt: int = Field(ge=1)
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0)
    token_spent: int = Field(default=0, ge=0)
    cost_spent: float = Field(default=0, ge=0)
    evidence_refs: tuple[str, ...] = ()
    error_code: Literal["WORKFLOW_FAILED"] | None = None


def finish_run(run: AgentRun, state: WorkflowState, now: datetime, *, failed=False):
    if run.status == WorkflowStatus.COMPLETED:
        raise ValueError("완료된 조사는 다시 실행 상태로 바꿀 수 없습니다.")
    status = WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
    return run.model_copy(update={"status": status, "state": state,
        "completed_at": now, "error_code": "WORKFLOW_FAILED" if failed else None,
        "safe_error_summary": "조사를 완료하지 못했습니다. 작업 이력을 확인해 주세요." if failed else None})
