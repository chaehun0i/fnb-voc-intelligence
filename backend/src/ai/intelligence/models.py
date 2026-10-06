"""ai/intelligence/models: 통합된 기능 책임, 기존 실행 계약 유지."""
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LLMErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TEMPORARY = "PROVIDER_TEMPORARY"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    DEADLINE_EXHAUSTED = "DEADLINE_EXHAUSTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    OUTPUT_SCHEMA_INVALID = "OUTPUT_SCHEMA_INVALID"
    OUTPUT_DOMAIN_INVALID = "OUTPUT_DOMAIN_INVALID"
    POLICY_DENIED = "POLICY_DENIED"
    CAPABILITY_UNSUPPORTED = "CAPABILITY_UNSUPPORTED"
    TRACE_UNAVAILABLE = "TRACE_UNAVAILABLE"


class LLMError(Exception):
    def __init__(self, code: LLMErrorCode):
        self.code = code
        super().__init__(code.value)

    @property
    def retryable(self):
        return self.code in {
            LLMErrorCode.PROVIDER_TEMPORARY, LLMErrorCode.RATE_LIMITED,
            LLMErrorCode.TIMEOUT, LLMErrorCode.PROVIDER_UNAVAILABLE,
        }


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

    @field_validator("request_id", "correlation_id", "tenant_id", "prompt_template", "prompt_version", "schema_version")
    @classmethod
    def safe_identity(cls, value):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
            raise ValueError("원문·개인정보 대신 안전한 식별자를 사용해 주세요.")
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


@dataclass(frozen=True)
class LLMCallRecord:
    call_id: str
    tenant_id: str
    request_id: str
    correlation_id: str
    incident_id: str | None
    config_version: int
    provider: str
    model: str
    task_type: str
    prompt_template: str
    prompt_version: str
    schema_version: str
    classification: str
    redacted: bool
    input_digest: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    latency_ms: int
    structured_retry: bool
    provider_retry: bool
    fallback: bool
    error_code: str | None
    created_at: datetime


class ExecutionBudget:
    def __init__(self, tokens, cost):
        self.token_limit, self.cost_limit = tokens, cost
        self.charged_tokens = self.input_tokens = self.output_tokens = 0
        self.charged_cost = 0
        self.structured_retries = self.provider_retries = 0

    def reserve(self, request, input_rate, output_rate):
        input_bound = len(request.prompt.encode("utf-8")) + len(request.output_schema_json.encode("utf-8")) + 256
        tokens = input_bound + request.max_output_tokens
        cost = (input_bound * input_rate + request.max_output_tokens * output_rate) / 1_000_000
        if self.charged_tokens + tokens > self.token_limit or self.charged_cost + cost > self.cost_limit:
            raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED)
        return tokens, cost

    def consume(self, usage, reservation, input_rate, output_rate):
        if usage is None:
            self.charged_tokens += reservation[0]
            self.charged_cost += reservation[1]
            return reservation[1]
        cost = (usage.input_tokens * input_rate + usage.output_tokens * output_rate) / 1_000_000
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.charged_tokens += usage.total_tokens
        self.charged_cost += cost
        return cost

    @property
    def usage(self):
        return LLMUsage(input_tokens=self.input_tokens, output_tokens=self.output_tokens)


class LLMProvider(Protocol):
    capability: ProviderCapability

    async def generate(self, request: ProviderRequest) -> ProviderResponse: ...
