"""검증은 조치 후 기록의 후보이며 외부 시스템 성공을 주장하지 않습니다."""
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from src.domain.workflows.models import SafeModel


class ActionExecutionRecord(SafeModel):
    execution_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    tenant_id: str
    incident_id: str
    agent_run_id: str
    action_id: str
    approval_id: str
    action_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_mode: Literal["INTERNAL_RECORD_ONLY"] = "INTERNAL_RECORD_ONLY"
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    started_at: datetime
    completed_at: datetime
    safe_result_summary: Literal["내부 실행 기록만 생성했습니다. 외부 시스템은 변경하지 않았습니다."] = "내부 실행 기록만 생성했습니다. 외부 시스템은 변경하지 않았습니다."
    config_version: int = Field(ge=1)
    correlation_id: str
    incident_version: int = Field(ge=1)

    @field_validator("started_at", "completed_at")
    @classmethod
    def aware(cls, value):
        if value.utcoffset() is None:
            raise ValueError("실행 시각에는 시간대가 필요합니다.")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if self.completed_at < self.started_at:
            raise ValueError("실행 기록의 시각 순서를 확인해 주세요.")
        return self


class VerificationEvidence(SafeModel):
    """인증된 내부 기록/시뮬레이션 source의 정규화된 사실만 받습니다."""
    evidence_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    tenant_id: str
    store: str
    agent_run_id: str
    execution_id: str
    action_id: str
    source_ref: str = Field(pattern=r"^internal-review:[a-f0-9-]{36}$")
    source_type: Literal["INTERNAL_REVIEW_RECORD"] = "INTERNAL_REVIEW_RECORD"
    observation_mode: Literal["SIMULATED"] = "SIMULATED"
    observed_at: datetime
    review_record_present: bool | None
    additional_evidence_refs: tuple[str, ...] = Field(default=(), max_length=20)

    _aware = field_validator("observed_at")(ActionExecutionRecord.aware.__func__)
    _refs = field_validator("additional_evidence_refs")(SafeModel.safe_refs.__func__)


class CriterionResult(SafeModel):
    code: Literal["REVIEW_RECORD_PRESENT", "ADDITIONAL_EVIDENCE_LIST"]
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]


class VerificationCandidate(SafeModel):
    verification_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    incident_id: str
    action_id: str
    execution_id: str
    criteria: str = Field(min_length=1, max_length=512)
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=20)
    criterion_results: tuple[CriterionResult, ...] = Field(min_length=2, max_length=2)
    result: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    confidence: float = Field(ge=0, le=1)
    summary: Literal["내부 시뮬레이션 기록의 검증 기준을 충족했습니다.", "내부 시뮬레이션 기록의 검증 기준을 충족하지 못했습니다.", "조치 후 검증 근거가 부족하거나 상충합니다."]
    reason_codes: tuple[Literal["CRITERIA_MET", "CRITERIA_NOT_MET", "EVIDENCE_MISSING", "EVIDENCE_STALE", "EVIDENCE_CONFLICTING", "UNSUPPORTED_CRITERIA"], ...]
    verified_at: datetime
    config_version: int = Field(ge=1)
    observation_mode: Literal["SIMULATED"] = "SIMULATED"

    _aware = field_validator("verified_at")(ActionExecutionRecord.aware.__func__)

    @model_validator(mode="after")
    def grounded(self):
        results = [c.result for c in self.criterion_results]
        expected = "INCONCLUSIVE" if "INCONCLUSIVE" in results else "FAIL" if "FAIL" in results else "PASS"
        if self.result != expected or (self.result in {"PASS", "FAIL"} and not self.evidence_ids):
            raise ValueError("검증 결과에는 기준별 판정과 조치 후 실제 기록 참조가 필요합니다.")
        return self
