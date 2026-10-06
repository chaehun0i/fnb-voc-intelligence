"""ai/workflow/models: 통합된 기능 책임, 기존 실행 계약 유지."""
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.ai.execution.models import (
    ActionExecutionRecord,
    VerificationCandidate,
    VerificationEvidence,
)
from src.ai.models import SafeModel

InvestigationAgent = Literal["HISTORY", "TRANSACTION", "INVENTORY"]
DataCapability = Literal["HISTORY_DATA", "TRANSACTION_DATA", "INVENTORY_DATA"]

TerminationReason = Literal["COMPLETED", "NO_NEW_EVIDENCE", "BUDGET_EXHAUSTED",
    "ITERATION_LIMIT", "POLICY_DENIED", "PAUSED", "STOPPED", "MANUAL_TAKEOVER", "INCOMPLETE"]


class LoopPolicy(SafeModel):
    version: Literal["bounded-investigation-1"] = "bounded-investigation-1"
    max_iterations: int = Field(strict=True, ge=1, le=3)
    max_operations: int = Field(strict=True, ge=1, le=50)
    token_budget: int = Field(strict=True, ge=100, le=100000)
    cost_budget: float = Field(ge=0.01, le=20, allow_inf_nan=False)
    timeout_seconds: int = Field(strict=True, ge=5, le=600)


class LoopTrace(SafeModel):
    policy: LoopPolicy
    termination: TerminationReason | None = None
    # counters remain exclusively on WorkflowState; no duplicate budget consumption.
    evidence_digest: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")
    new_evidence: bool = False


class AgentRunManifest(SafeModel):
    workflow_id: str
    workflow_version: str = Field(pattern=r"^(history-(v1|evidence-v2|capa-v3|verification-v4)|multi-investigation-v5)$")
    graph_version: Literal["serviq-graph-1"] = "serviq-graph-1"
    config_version: int = Field(strict=True, ge=1)
    agent_registry_version: Literal["investigation-1"] = "investigation-1"
    context_policy_version: Literal["minimal-context-1"] = "minimal-context-1"
    loop_policy_version: Literal["bounded-investigation-1"] = "bounded-investigation-1"
    harness_policy_version: Literal["operation-gate-1"] = "operation-gate-1"
    agent_versions: tuple[tuple[InvestigationAgent, Literal["1"]], ...] = ()
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def unique_agents(self):
        if len({a for a, _ in self.agent_versions}) != len(self.agent_versions):
            raise ValueError("MANIFEST_AGENT_DUPLICATE")
        return self


class AgentDefinition(SafeModel):
    agent_type: InvestigationAgent
    agent_version: Literal["1"] = "1"
    business_label: Literal["과거 사례 조사", "거래 내역 조사", "재고 조사"]
    purpose: Literal["RELATED_HISTORY", "TRANSACTION_SIGNALS", "INVENTORY_SIGNALS"]
    supported_categories: tuple[str, ...] = ("GENERAL", "UNKNOWN", "TRANSACTION", "COLD_CHAIN", "FOOD_SAFETY", "SUPPLIER_LOT")
    required_capabilities: tuple[DataCapability, ...] = Field(min_length=1)
    optional_capabilities: tuple[DataCapability, ...] = ()
    output_schema_version: Literal["investigation-1"] = "investigation-1"
    parallel_safe: bool = True
    default_budget_profile: Literal["READ_ONLY_BOUNDED"] = "READ_ONLY_BOUNDED"
    enabled: bool = True


class TenantCapability(SafeModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    capability: DataCapability
    available: bool
    source: Literal["AUTHORIZED_HISTORY_SEARCH", "SYNTHETIC_OPERATIONAL_FIXTURE"]
    health: Literal["HEALTHY", "UNAVAILABLE"]
    freshness: Literal["FRESH", "STALE", "UNKNOWN"]
    checked_at: datetime

    @field_validator("checked_at")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("Capability 확인 시각에 시간대가 필요합니다.")
        return value


class AgentSelection(SafeModel):
    registry_version: Literal["investigation-1"] = "investigation-1"
    selected: tuple[AgentDefinition, ...] = Field(default=(), max_length=3)
    excluded: tuple[InvestigationAgent, ...] = ()
    capabilities: tuple[TenantCapability, ...] = Field(default=(), max_length=3)


class ContextReference(SafeModel):
    source_ref: str = Field(pattern=r"^(review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}$")
    source_at: datetime | None = None
    provenance: Literal["AUTHORIZED_HISTORY_SEARCH", "SYNTHETIC_OPERATIONAL_FIXTURE"]

    @field_validator("source_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Context 출처 시각에는 시간대가 필요합니다.")
        return value


class AgentContextPack(SafeModel):
    agent_type: InvestigationAgent
    tenant_id: str = Field(min_length=1, max_length=128)
    incident_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    category: str = Field(pattern=r"^[A-Z_]{1,64}$")
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    objective: Literal["READ_ONLY_INVESTIGATION"] = "READ_ONLY_INVESTIGATION"
    data_policy: Literal["REFERENCE_ONLY"] = "REFERENCE_ONLY"
    policy_version: Literal["minimal-context-1"] = "minimal-context-1"
    window_start: datetime
    window_end: datetime
    fetched_at: datetime
    freshness: Literal["FRESH", "STALE", "UNKNOWN"]
    references: tuple[ContextReference, ...] = Field(default=(), max_length=20)
    excluded_count: int = Field(default=0, ge=0)
    budget_bytes: int = Field(ge=256, le=20000)
    used_bytes: int = Field(ge=0)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def bounds(self):
        import hashlib
        import json
        document = self.model_dump(mode="json", exclude={"digest", "used_bytes"})
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        if (self.used_bytes != len(encoded) or self.used_bytes > self.budget_bytes
                or self.digest != hashlib.sha256(encoded).hexdigest()
                or any(d.utcoffset() is None for d in (self.window_start, self.window_end, self.fetched_at))
                or not self.window_start <= self.window_end <= self.fetched_at):
            raise ValueError("CONTEXT_INTEGRITY_INVALID")
        prefix = {"HISTORY": "review:", "TRANSACTION": "transaction:", "INVENTORY": "inventory:"}[self.agent_type]
        if any(not r.source_ref.startswith(prefix) for r in self.references):
            raise ValueError("CONTEXT_AGENT_SOURCE_MISMATCH")
        return self


class WorkflowStatus(StrEnum):
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class EvidenceCandidate(SafeModel):
    source_ref: str = Field(pattern=r"^(review|transaction|inventory):[A-Za-z0-9_.:-]{1,128}$")
    source_type: Literal["VOC_REVIEW", "TRANSACTION", "INVENTORY"] = "VOC_REVIEW"
    rank: int = Field(ge=1, le=20)
    retrieved_at: datetime
    tenant_id: str | None = Field(default=None, min_length=1, max_length=128)
    store: str | None = Field(default=None, min_length=1, max_length=128)
    provenance: tuple[Literal["lexical", "vector", "hybrid", "legacy_reference", "synthetic_operational"], ...] = ("legacy_reference",)
    source_at: datetime | None = None
    stance: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"] = "NEUTRAL"
    observation_code: Literal["RELATED_HISTORY_MATCH", "REFERENCE_ONLY", "REFUND_SIGNAL", "CANCEL_SIGNAL", "STOCK_SHORTAGE", "STOCK_ADJUSTMENT"] = "REFERENCE_ONLY"
    observed_stances: tuple[Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"], ...] = ()
    contributing_agents: tuple[InvestigationAgent, ...] = ()

    @field_validator("retrieved_at", "source_at")
    @classmethod
    def aware(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("검색 시각에 시간대를 포함해 주세요.")
        return value


class Finding(SafeModel):
    code: Literal["RELATED_HISTORY_FOUND", "TRANSACTION_SIGNAL_FOUND", "INVENTORY_SIGNAL_FOUND"] = "RELATED_HISTORY_FOUND"
    evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=20)


class EvidenceGap(SafeModel):
    code: Literal["NO_AUTHORIZED_HISTORY", "LLM_POLICY_DENIED", "LLM_UNAVAILABLE",
                  "INSUFFICIENT_SOURCE_COVERAGE", "CONFLICTING_EVIDENCE", "RCA_DISABLED", "RCA_BUDGET_EXHAUSTED",
                  "CAPABILITY_UNAVAILABLE", "SOURCE_UNAVAILABLE", "SOURCE_STALE", "BRANCH_FAILED", "NO_EVIDENCE_FOUND", "BRANCH_BUDGET_EXHAUSTED"]
    agent_type: InvestigationAgent | None = None


class OperationalObservation(SafeModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    agent_type: Literal["TRANSACTION", "INVENTORY"]
    source_ref: str = Field(pattern=r"^(transaction|inventory):[A-Za-z0-9_.:-]{1,128}$")
    observed_at: datetime
    signal: Literal["REFUND_SIGNAL", "CANCEL_SIGNAL", "STOCK_SHORTAGE", "STOCK_ADJUSTMENT"]
    stance: Literal["SUPPORTING", "CONTRADICTING", "NEUTRAL"] = "NEUTRAL"
    source: Literal["SYNTHETIC_OPERATIONAL_FIXTURE"] = "SYNTHETIC_OPERATIONAL_FIXTURE"

    @model_validator(mode="after")
    def integrity(self):
        if (self.observed_at.utcoffset() is None or not self.source_ref.startswith(self.agent_type.lower()+":")
                or (self.signal.startswith("STOCK") != (self.agent_type == "INVENTORY"))):
            raise ValueError("OPERATIONAL_SOURCE_INVALID")
        return self


class InvestigationResult(SafeModel):
    agent_type: InvestigationAgent
    agent_version: Literal["1"] = "1"
    branch_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    tenant_id: str
    incident_id: str
    store: str
    status: Literal["SUCCESS", "FAILED", "UNAVAILABLE", "NO_EVIDENCE", "STALE"]
    findings: tuple[Finding, ...] = ()
    evidence_candidates: tuple[EvidenceCandidate, ...] = Field(default=(), max_length=20)
    evidence_gaps: tuple[EvidenceGap, ...] = ()
    retryable: bool = False
    uncertainty: Literal["OBSERVATIONS_NOT_CAUSE", "MISSING_EVIDENCE"]
    started_at: datetime
    completed_at: datetime
    context_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def integrity(self):
        if (any(e.tenant_id != self.tenant_id or e.store != self.store for e in self.evidence_candidates)
                or any(e.source_type != ("VOC_REVIEW" if self.agent_type == "HISTORY" else self.agent_type)
                    for e in self.evidence_candidates)
                or (self.status != "SUCCESS" and self.evidence_candidates)
                or self.started_at.utcoffset() is None or self.completed_at.utcoffset() is None
                or self.completed_at < self.started_at
                or not {r for f in self.findings for r in f.evidence_refs} <= {e.source_ref for e in self.evidence_candidates}):
            raise ValueError("BRANCH_RESULT_INVALID")
        return self


class NormalizedEvidence(EvidenceCandidate):
    tenant_id: str = Field(min_length=1, max_length=128)
    store: str = Field(min_length=1, max_length=128)
    agent_run_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    step_name: Literal["history_investigation", "investigation_fan_in"] = "history_investigation"

    @model_validator(mode="after")
    def source_identity(self):
        prefix = {"VOC_REVIEW": "review:", "TRANSACTION": "transaction:", "INVENTORY": "inventory:"}[self.source_type]
        if self.source_ref != prefix+self.source_id or not self.provenance:
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
    loop: LoopTrace | None = None
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
    selection: AgentSelection | None = None
    contexts: tuple[AgentContextPack, ...] = Field(default=(), max_length=3)
    branches: tuple[InvestigationResult, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def evidence_integrity(self):
        selected = {a.agent_type for a in self.selection.selected} if self.selection else set()
        if (len(selected) != len(self.selection.selected if self.selection else ())
                or len({c.agent_type for c in self.contexts}) != len(self.contexts)
                or len({b.agent_type for b in self.branches}) != len(self.branches)
                or {c.agent_type for c in self.contexts} != selected
                or not {b.agent_type for b in self.branches} <= selected
                or any(c.tenant_id != self.tenant_id or c.incident_id != self.incident_id for c in self.contexts)
                or any(b.tenant_id != self.tenant_id or b.incident_id != self.incident_id
                    or b.context_digest != next(c.digest for c in self.contexts if c.agent_type == b.agent_type)
                    or b.store != next(c.store for c in self.contexts if c.agent_type == b.agent_type) for b in self.branches)):
            raise ValueError("INVESTIGATION_LINEAGE_INVALID")
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
    manifest: AgentRunManifest | None = None
    agent_run_id: str
    tenant_id: str
    incident_id: str
    workflow_id: str
    job_id: str
    correlation_id: str
    config_version: int = Field(ge=1)
    jev_decision_id: str
    workflow_version: Literal["history-v1", "history-evidence-v2", "history-capa-v3", "history-verification-v4", "multi-investigation-v5"] = "history-v1"
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
        if self.manifest and (self.manifest.workflow_id != self.workflow_id
                or self.manifest.workflow_version != self.workflow_version
                or self.manifest.config_version != self.config_version
                or self.manifest.agent_versions != tuple((a.agent_type, a.agent_version)
                    for a in (self.state.selection.selected if self.state.selection else ()))):
            raise ValueError("MANIFEST_LINEAGE_INVALID")
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
