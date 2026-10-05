"""운영 UI에 필요한 참조·정규화 결과만 공개하는 HTTP DTO입니다."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FindingResponse(BaseModel):
    code: Literal["RELATED_HISTORY_FOUND"]
    evidence_refs: list[str]


class EvidenceCandidateResponse(BaseModel):
    source_ref: str
    source_type: Literal["VOC_REVIEW"]
    rank: int
    retrieved_at: datetime


class EvidenceGapResponse(BaseModel):
    code: Literal["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE"]


class AgentRunResponse(BaseModel):
    agent_run_id: str
    incident_id: str
    workflow_id: str
    job_id: str
    correlation_id: str
    config_version: int
    jev_decision_id: str
    workflow_version: Literal["history-v1"]
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    started_at: datetime
    completed_at: datetime | None
    error_code: Literal["WORKFLOW_FAILED"] | None
    safe_error_summary: str | None
    route: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    findings: list[FindingResponse]
    evidence_candidates: list[EvidenceCandidateResponse]
    evidence_gaps: list[EvidenceGapResponse]
    token_spent: int
    cost_spent: float
    iteration: int
    tool_call_count: int


class AgentStepResponse(BaseModel):
    agent_run_id: str
    sequence: int
    node_name: Literal["validate_context", "history_investigation", "persist_result"]
    attempt: int
    status: Literal["RUNNING", "COMPLETED", "FAILED"]
    started_at: datetime
    completed_at: datetime
    latency_ms: float
    token_spent: int
    cost_spent: float
    evidence_refs: list[str]
    error_code: str | None


class AgentRunDetailResponse(AgentRunResponse):
    steps: list[AgentStepResponse]


class AgentRunHistoryResponse(BaseModel):
    runs: list[AgentRunResponse]
    limit: int
    offset: int
    has_more: bool
