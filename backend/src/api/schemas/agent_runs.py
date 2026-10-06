"""운영 UI에 필요한 참조·정규화 결과만 공개하는 HTTP DTO입니다."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from src.domain.workflows.verification import VerificationCandidate


class FindingResponse(BaseModel):
    code: Literal["RELATED_HISTORY_FOUND"]
    evidence_refs: list[str]


class EvidenceCandidateResponse(BaseModel):
    source_ref: str
    source_type: Literal["VOC_REVIEW"]
    rank: int
    retrieved_at: datetime
    provenance: list[Literal["lexical", "vector", "hybrid", "legacy_reference"]] = []
    source_at: datetime | None = None
    stance: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"] = "NEUTRAL"
    observation_code: Literal["RELATED_HISTORY_MATCH", "REFERENCE_ONLY"] = "REFERENCE_ONLY"


class NormalizedEvidenceResponse(EvidenceCandidateResponse):
    source_id: str
    agent_run_id: str
    step_name: Literal["history_investigation"]


class EvidenceGapResponse(BaseModel):
    code: Literal["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE",
                  "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "RCA_DISABLED", "RCA_BUDGET_EXHAUSTED"]


class SufficiencyResponse(BaseModel):
    status: Literal["SUFFICIENT", "INSUFFICIENT", "CONFLICTING"]
    policy_version: Literal["history-support-v1"]
    evaluated_dimensions: list[Literal["SOURCE_COVERAGE", "OBSERVATION_SUPPORT", "CONTRADICTION"]]
    supporting_refs: list[str]
    contradicting_refs: list[str]
    evidence_gaps: list[EvidenceGapResponse]
    reason_codes: list[Literal["NO_EVIDENCE", "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "SUFFICIENT_HISTORY_SUPPORT"]]


class RCAResponse(BaseModel):
    candidate_id: str
    code: Literal["REPEATED_HISTORY_SIGNAL"]
    hypothesis: str
    confidence: float
    supporting_refs: list[str]
    contradicting_refs: list[str]
    unresolved_gaps: list[EvidenceGapResponse]
    provenance: Literal["HISTORY_HYPOTHESIS_NOT_CONFIRMED"]
    generated_by: Literal["DETERMINISTIC", "LLM_GATEWAY"]
    config_version: int
    jev_decision_id: str
    llm_request_id: str | None


class CAPAResponse(BaseModel):
    capa_proposal_id: str
    incident_id: str
    agent_run_id: str
    rca_candidate_id: str
    summary: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    expected_effect: str
    verification_criteria: str
    supporting_evidence_ids: list[str]
    required_approval: bool
    proposed_action_type: Literal["MANUAL_HISTORY_REVIEW"]
    target_reference: str
    assumptions: list[str]
    uncertainties: list[str]
    config_version: int
    decision_reference: str
    status: Literal["PROPOSED", "APPLIED"]


class ApprovalTraceResponse(BaseModel):
    approval_id: str
    action_ids: list[str]
    action_digest: str
    config_version: int
    incident_version: int
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    phase: Literal["WAITING_APPROVAL", "READY_TO_EXECUTE", "REJECTED"]
    waiting_since: datetime
    resumed_at: datetime | None
    decision_actor: str | None
    decision_reason_code: Literal["HUMAN_APPROVED", "HUMAN_REJECTED"] | None


class ExecutionTraceResponse(BaseModel):
    execution_id: str
    incident_id: str
    agent_run_id: str
    action_id: str
    approval_id: str
    action_digest: str
    execution_mode: Literal["INTERNAL_RECORD_ONLY"]
    status: Literal["SUCCEEDED"]
    started_at: datetime
    completed_at: datetime
    safe_result_summary: str
    config_version: int
    correlation_id: str
    incident_version: int


class PostActionEvidenceResponse(BaseModel):
    evidence_id: str
    agent_run_id: str
    execution_id: str
    action_id: str
    source_ref: str
    source_type: Literal["INTERNAL_REVIEW_RECORD"]
    observation_mode: Literal["SIMULATED"]
    observed_at: datetime
    review_record_present: bool | None
    additional_evidence_refs: list[str]


class AgentRunResponse(BaseModel):
    agent_run_id: str
    incident_id: str
    workflow_id: str
    job_id: str
    correlation_id: str
    config_version: int
    jev_decision_id: str
    workflow_version: Literal["history-v1", "history-evidence-v2", "history-capa-v3", "history-verification-v4"]
    status: Literal["RUNNING", "WAITING_APPROVAL", "COMPLETED", "FAILED"]
    started_at: datetime
    completed_at: datetime | None
    error_code: Literal["WORKFLOW_FAILED"] | None
    safe_error_summary: str | None
    route: str
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    findings: list[FindingResponse]
    evidence_candidates: list[EvidenceCandidateResponse]
    evidence_gaps: list[EvidenceGapResponse]
    normalized_evidence: list[NormalizedEvidenceResponse] = []
    sufficiency: SufficiencyResponse | None = None
    rca_candidates: list[RCAResponse] = []
    capa_proposals: list[CAPAResponse] = []
    approval: ApprovalTraceResponse | None = None
    execution: ExecutionTraceResponse | None = None
    verification: VerificationCandidate | None = None
    verification_evidence: list[PostActionEvidenceResponse] = []
    resulting_incident_status: Literal["EXECUTING", "VERIFYING", "RESOLVED", "REOPENED"] | None = None
    token_spent: int
    cost_spent: float
    iteration: int
    tool_call_count: int


class AgentStepResponse(BaseModel):
    agent_run_id: str
    sequence: int
    node_name: Literal["validate_context", "history_investigation", "normalize_evidence",
                       "evaluate_sufficiency", "rca_investigation", "persist_result", "capa_proposal",
                       "apply_capa", "request_approval", "approval_interrupt", "approval_result",
                       "internal_execution", "begin_verification", "verification", "apply_verification"]
    attempt: int
    status: Literal["RUNNING", "WAITING_APPROVAL", "COMPLETED", "FAILED"]
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
