"""SDK 타입이나 credential을 포함하지 않는 불변 실행 계약입니다."""
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class LLMTaskType(StrEnum):
    TRIAGE = "TRIAGE"
    RCA = "RCA"
    CAPA = "CAPA"
    SUMMARY = "SUMMARY"
    CLASSIFICATION = "CLASSIFICATION"
    EXTRACTION = "EXTRACTION"


class ModelClass(StrEnum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    REASONING = "REASONING"


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    PII = "PII"
    RESTRICTED = "RESTRICTED"


class LLMIntent(FrozenModel):
    request_id: str = Field(min_length=1, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    incident_id: str | None = None
    task_type: LLMTaskType
    model_class: ModelClass = ModelClass.STANDARD
    input_references: tuple[str, ...] = ()
    # JSON 문자열로 보관해 frozen 모델 내부의 가변 dict 변경도 방지합니다.
    payload_json: str = Field(min_length=2, max_length=16000, repr=False)
    output_schema_json: str = Field(min_length=2, max_length=16000, repr=False)
    schema_version: str = Field(min_length=1, max_length=64)
    prompt_template: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=64)
    config_version: int = Field(ge=0)
    deadline: datetime
    max_output_tokens: int = Field(default=1024, ge=1, le=8192)
    token_budget: int = Field(default=8192, ge=1, le=100000)
    cost_budget_usd: float = Field(default=1, gt=0, le=20)
    fallback_allowed: bool = False
    classification: DataClassification = DataClassification.INTERNAL
    free_text_reviewed: bool = False

    @field_validator("payload_json", "output_schema_json")
    @classmethod
    def json_object(cls, value):
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("JSON 객체를 사용해 주세요.")  # noqa: TRY004 — Pydantic 검증 오류로 변환합니다.
        return json.dumps(parsed, sort_keys=True, ensure_ascii=False, allow_nan=False)

    @field_validator("deadline")
    @classmethod
    def aware_deadline(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("시간대가 포함된 deadline이 필요합니다.")
        return value


class ProviderCapability(FrozenModel):
    provider: Literal["fake", "gemini", "ollama"]
    hosted: bool
    structured_output: bool = True
    tool_calling: bool = False
    vision: bool = False
    streaming: bool = False
    context_limit: int = Field(default=32000, ge=1)
    model_classes: tuple[ModelClass, ...] = tuple(ModelClass)


class ProviderRequest(FrozenModel):
    request_id: str
    tenant_id: str
    model: str = Field(min_length=1, max_length=128)
    prompt: str = Field(min_length=1, max_length=20000, repr=False)
    output_schema_json: str = Field(repr=False)
    timeout_seconds: float = Field(gt=0, le=600)
    max_output_tokens: int = Field(ge=1, le=8192)
    repair: bool = False


class LLMUsage(FrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)

    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens


class ProviderResponse(FrozenModel):
    content: str = Field(max_length=65536, repr=False)
    usage: LLMUsage
    finish_reason: Literal["STOP", "LIMIT", "BLOCKED", "UNKNOWN"] = "UNKNOWN"


class LLMResult(FrozenModel):
    request_id: str
    provider: str
    model: str
    config_version: int
    structured_json: str = Field(repr=False)
    usage: LLMUsage
    structured_retry_count: int = 0
    provider_retry_count: int = 0
    fallback_used: bool = False
    estimated_cost_usd: float = 0
