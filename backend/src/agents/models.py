"""원문 대신 참조와 정규화 결과를 보관하는 SDK 독립 실행 계약입니다."""
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.agents.safe import SafeModel
from src.agents.verification_contracts import (
    ActionExecutionRecord,
    VerificationCandidate,
    VerificationEvidence,
)


class WorkflowStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceCandidate(SafeModel):
    source_ref: str = Field(pattern=r"^review:[A-Za-z0-9_.:-]{1,128}$")
    source_type: Literal["VOC_REVIEW"] = "VOC_REVIEW"
    rank: int = Field(ge=1, le=20)
    retrieved_at: datetime
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)
    store: str | None = Field(default=None, min_length=1, max_length=128)
    provenance: tuple[Literal["lexical", "vector", "hybrid", "legacy_reference"], ...] = ("legacy_reference",)
    source_at: datetime | None = None
    stance: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"] = "NEUTRAL"
    observation_code: Literal["RELATED_HISTORY_MATCH", "REFERENCE_ONLY"] = "REFERENCE_ONLY"

    @field_validator("retrieved_at", "source_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("검색 시각에 시간대를 포함해 주세요.")
        return value


class Finding(SafeModel):
    code: Literal["RELATED_HISTORY_FOUND"] = "RELATED_HISTORY_FOUND"
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=20)


class EvidenceGap(SafeModel):
    code: Literal["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE",
                  "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "RCA_DISABLED", "RCA_BUDGET_EXHAUSTED"]


class NormalizedEvidence(EvidenceCandidate):
    tenant_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    agent_run_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    step_name: Literal["history_investigation"] = "history_investigation"

    @model_validator(mode="after")
    def source_identity(self):
        if self.source_ref != "review:"+self.source_id or not self.provenance:
            raise ValueError("근거의 원본 참조와 출처를 확인해 주세요.")
        return self


class SufficiencyPolicy(SafeModel):
    # 두 독립 이력은 반복 불만 가설의 최소 기준이며 물리적 근본 원인의 확정 기준이 아닙니다.
    policy_version: Literal["history-support-v1"] = "history-support-v1"
    minimum_sources: int = Field(default=2, ge=2, le=20)
    required_source_types: tuple[Literal["VOC_REVIEW"], ...] = ("VOC_REVIEW",)


class SufficiencyResult(SafeModel):
    status: Literal["SUFFICIENT", "INSUFFICIENT", "CONFLICTING"]
    policy_version: Literal["history-support-v1"] = "history-support-v1"
    evaluated_dimensions: tuple[Literal["SOURCE_COVERAGE", "OBSERVATION_SUPPORT", "CONTRADICTION"], ...]
    supporting_refs: tuple[str, ...] = ()
    contradicting_refs: tuple[str, ...] = ()
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    reason_codes: tuple[Literal["NO_EVIDENCE", "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE",
                                "SUFFICIENT_HISTORY_SUPPORT"], ...]

    @field_validator("supporting_refs", "contradicting_refs")
    @classmethod
    def validate_refs(cls, value):
        return cls.safe_refs(value)

    @property
    def allows_rca(self):
        return self.status == "SUFFICIENT"


class RCACandidate(SafeModel):
    candidate_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    code: Literal["REPEATED_HISTORY_SIGNAL"] = "REPEATED_HISTORY_SIGNAL"
    hypothesis: Literal["반복 불만 이력이 관측되어 공통 원인에 대한 추가 조사가 필요합니다."] = "반복 불만 이력이 관측되어 공통 원인에 대한 추가 조사가 필요합니다."
    confidence: float = Field(ge=0, le=1)
    supporting_refs: tuple[str, ...] = Field(min_length=1, max_length=20)
    contradicting_refs: tuple[str, ...] = Field(default=(), max_length=20)
    unresolved_gaps: tuple[EvidenceGap, ...] = ()
    provenance: Literal["HISTORY_HYPOTHESIS_NOT_CONFIRMED"] = "HISTORY_HYPOTHESIS_NOT_CONFIRMED"
    generated_by: Literal["DETERMINISTIC", "LLM_GATEWAY"]
    config_version: int = Field(ge=1)
    jev_decision_id: str = Field(min_length=1, max_length=128)
    llm_request_id: str | None = Field(default=None, max_length=128)

    @field_validator("supporting_refs", "contradicting_refs")
    @classmethod
    def validate_refs(cls, value):
        return cls.safe_refs(value)

    @model_validator(mode="after")
    def disjoint(self):
        if set(self.supporting_refs) & set(self.contradicting_refs):
            raise ValueError("같은 근거를 지지와 반대로 동시에 사용할 수 없습니다.")
        return self


class CAPAProposal(SafeModel):
    capa_proposal_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    tenant_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(min_length=1, max_length=128)
    agent_run_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    rca_candidate_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    summary: Literal["관련 과거 사례와 현장 절차를 담당자가 재검토합니다."] = "관련 과거 사례와 현장 절차를 담당자가 재검토합니다."
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    expected_effect: Literal["반복 불만의 공통 원인과 추가 조사 범위를 확인합니다."] = "반복 불만의 공통 원인과 추가 조사 범위를 확인합니다."
    verification_criteria: Literal["담당자의 이력·절차 재검토 기록과 추가 근거 목록이 존재해야 합니다."] = "담당자의 이력·절차 재검토 기록과 추가 근거 목록이 존재해야 합니다."
    supporting_evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    required_approval: bool = True
    proposed_action_type: Literal["MANUAL_HISTORY_REVIEW"] = "MANUAL_HISTORY_REVIEW"
    target_reference: str = Field(min_length=1, max_length=128)
    assumptions: tuple[Literal["HISTORY_HYPOTHESIS_NOT_CONFIRMED"], ...] = ("HISTORY_HYPOTHESIS_NOT_CONFIRMED",)
    uncertainties: tuple[Literal["PHYSICAL_CAUSE_UNCONFIRMED"], ...] = ("PHYSICAL_CAUSE_UNCONFIRMED",)
    config_version: int = Field(ge=1)
    decision_reference: str = Field(min_length=1, max_length=128)
    status: Literal["PROPOSED", "APPLIED"] = "PROPOSED"

    @field_validator("supporting_evidence_ids")
    @classmethod
    def validate_refs(cls, value):
        return cls.safe_refs(value)

    @model_validator(mode="after")
    def target(self):
        if self.target_reference != self.incident_id:
            raise ValueError("지원되는 조치 대상은 같은 Incident의 수동 검토뿐입니다.")
        return self


class ApprovalTrace(SafeModel):
    approval_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    action_ids: tuple[str, ...] = Field(min_length=1, max_length=3)
    action_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_version: int = Field(ge=1)
    incident_version: int = Field(ge=1)
    status: Literal["PENDING", "APPROVED", "REJECTED"] = "PENDING"
    phase: Literal["WAITING_APPROVAL", "READY_TO_EXECUTE", "REJECTED"] = "WAITING_APPROVAL"
    waiting_since: datetime
    resumed_at: datetime | None = None
    decision_actor: str | None = Field(default=None, max_length=128)
    decision_reason_code: Literal["HUMAN_APPROVED", "HUMAN_REJECTED"] | None = None

    @field_validator("waiting_since", "resumed_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("승인 시각에는 시간대가 필요합니다.")
        return value


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
    normalized_evidence: tuple[NormalizedEvidence, ...] = Field(default=(), max_length=20)
    sufficiency: SufficiencyResult | None = None
    rca_candidates: tuple[RCACandidate, ...] = Field(default=(), max_length=5)
    capa_proposals: tuple[CAPAProposal, ...] = Field(default=(), max_length=3)
    approval: ApprovalTrace | None = None
    execution: ActionExecutionRecord | None = None
    verification_evidence: tuple[VerificationEvidence, ...] = Field(default=(), max_length=20)
    verification: VerificationCandidate | None = None
    resulting_incident_status: Literal["EXECUTING", "VERIFYING", "RESOLVED", "REOPENED"] | None = None
    rca_completed: bool = False
    iteration: int = Field(default=0, ge=0, le=20)
    tool_call_count: int = Field(default=0, ge=0, le=50)
    token_spent: int = Field(default=0, ge=0)
    cost_spent: float = Field(default=0, ge=0)
    config_version: int = Field(ge=1)
    status: WorkflowStatus = WorkflowStatus.RUNNING

    @model_validator(mode="after")
    def evidence_integrity(self):
        available = {e.source_ref: e for e in self.normalized_evidence}
        if len(available) != len(self.normalized_evidence) or any(
            e.tenant_id != self.tenant_id or e.agent_run_id != self.agent_run_id for e in available.values()):
            raise ValueError("정규화 근거의 조직·실행·중복 참조를 확인해 주세요.")
        if self.sufficiency and not set(self.sufficiency.supporting_refs+self.sufficiency.contradicting_refs).issubset(available):
            raise ValueError("충분성 판정은 실제 근거만 참조해야 합니다.")
        for candidate in self.rca_candidates:
            if not self.sufficiency or not self.sufficiency.allows_rca or candidate.config_version != self.config_version:
                raise ValueError("RCA gate와 설정 버전을 확인해 주세요.")
            if (not set(candidate.supporting_refs+candidate.contradicting_refs).issubset(available)
                or any(available[r].stance != "SUPPORTING" for r in candidate.supporting_refs)
                or any(available[r].stance != "CONTRADICTING" for r in candidate.contradicting_refs)):
                raise ValueError("RCA가 존재하지 않거나 반대 성격의 근거를 지지로 참조할 수 없습니다.")
        causes = {c.candidate_id: c for c in self.rca_candidates}
        for proposal in self.capa_proposals:
            if (proposal.rca_candidate_id not in causes
                    or proposal.tenant_id != self.tenant_id or proposal.incident_id != self.incident_id
                    or proposal.agent_run_id != self.agent_run_id or proposal.config_version != self.config_version
                    or not set(proposal.supporting_evidence_ids).issubset(causes[proposal.rca_candidate_id].supporting_refs)):
                raise ValueError("CAPA는 같은 실행의 RCA와 실제 지지 근거를 참조해야 합니다.")
        if self.approval and (self.approval.config_version != self.config_version
                or set(self.approval.action_ids) != {p.capa_proposal_id for p in self.capa_proposals}
                or any(p.status != "APPLIED" for p in self.capa_proposals)):
            raise ValueError("Approval은 같은 실행에 저장된 조치만 참조해야 합니다.")
        if self.execution:
            e = self.execution
            if (not self.approval or self.approval.status != "APPROVED"
                    or e.tenant_id != self.tenant_id or e.incident_id != self.incident_id
                    or e.agent_run_id != self.agent_run_id or e.config_version != self.config_version
                    or e.approval_id != self.approval.approval_id or e.action_digest != self.approval.action_digest
                    or e.action_id not in self.approval.action_ids):
                raise ValueError("내부 실행 기록의 승인·조직·설정 lineage를 확인해 주세요.")
        for evidence in self.verification_evidence:
            if (not self.execution or evidence.tenant_id != self.tenant_id
                    or evidence.agent_run_id != self.agent_run_id
                    or evidence.execution_id != self.execution.execution_id
                    or evidence.action_id != self.execution.action_id
                    or not self.capa_proposals or evidence.store != self.capa_proposals[0].store
                    or not set(evidence.additional_evidence_refs) <= {e.source_ref for e in self.normalized_evidence}):
                raise ValueError("복원된 검증 근거의 조직·매장·실행·원본 참조가 일치해야 합니다.")
        if self.verification and (not self.execution or self.verification.execution_id != self.execution.execution_id
                or self.verification.action_id != self.execution.action_id
                or self.verification.incident_id != self.incident_id or self.verification.config_version != self.config_version
                or not set(self.verification.evidence_ids) <= {e.evidence_id for e in self.verification_evidence}):
            raise ValueError("검증 후보는 같은 실행의 실제 조치 후 근거를 참조해야 합니다.")
        return self


class AgentRun(SafeModel):
    agent_run_id: str
    tenant_id: str
    incident_id: str
    workflow_id: str
    job_id: str
    correlation_id: str
    config_version: int = Field(ge=1)
    jev_decision_id: str
    workflow_version: Literal["history-v1", "history-evidence-v2", "history-capa-v3", "history-verification-v4"] = "history-v1"
    requested_by: str | None = Field(default=None, max_length=128)
    delegated_roles: tuple[str, ...] = ()
    delegated_store_scope: tuple[str, ...] = ()
    initial_incident_version: int = Field(default=0, ge=0)
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
        if any(c.jev_decision_id != self.jev_decision_id for c in self.state.rca_candidates):
            raise ValueError("RCA Decision 원본을 확인해 주세요.")
        if any(c.decision_reference != self.jev_decision_id for c in self.state.capa_proposals):
            raise ValueError("CAPA Decision 원본을 확인해 주세요.")
        return self

    @field_validator("started_at", "completed_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("실행 시각에 시간대를 포함해 주세요.")
        return value


class AgentStep(SafeModel):
    agent_run_id: str
    sequence: int = Field(ge=1, le=15)
    node_name: Literal["validate_context", "history_investigation", "normalize_evidence",
                       "evaluate_sufficiency", "rca_investigation", "persist_result", "capa_proposal",
                       "apply_capa", "request_approval", "approval_interrupt", "approval_result",
                       "internal_execution", "begin_verification", "verification", "apply_verification"]
    attempt: int = Field(ge=1)
    status: WorkflowStatus
    started_at: datetime
    completed_at: datetime
    latency_ms: float = Field(ge=0)
    token_spent: int = Field(default=0, ge=0)
    cost_spent: float = Field(default=0, ge=0)
    evidence_refs: tuple[str, ...] = ()
    error_code: Literal["WORKFLOW_FAILED"] | None = None
    result: WorkflowState | None = None


def finish_run(run: AgentRun, state: WorkflowState, now: datetime, *, failed=False):
    if run.status == WorkflowStatus.COMPLETED:
        raise ValueError("완료된 조사는 다시 실행 상태로 바꿀 수 없습니다.")
    status = WorkflowStatus.FAILED if failed else WorkflowStatus.COMPLETED
    return run.model_copy(update={"status": status, "state": state,
        "completed_at": now, "error_code": "WORKFLOW_FAILED" if failed else None,
        "safe_error_summary": "조사를 완료하지 못했습니다. 작업 이력을 확인해 주세요." if failed else None})
