"""운영 설정의 HTTP 입력·응답 타입이며 Domain 모델과 구분합니다."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class RiskApprovalInput(StrictModel):
    LOW: bool
    MEDIUM: bool
    HIGH: bool
    CRITICAL: bool


class LLMModelBindingInput(StrictModel):
    provider: Literal["gemini", "ollama"]
    model_class: Literal["FAST", "STANDARD", "REASONING"]
    model: str = Field(min_length=1, max_length=128)
    input_usd_per_million: float = Field(ge=0, allow_inf_nan=False)
    output_usd_per_million: float = Field(ge=0, allow_inf_nan=False)


class RuntimeConfigInput(StrictModel):
    default_llm_provider: Literal["gemini", "ollama"]
    fallback_llm_provider: Literal["gemini", "ollama"]
    jev_enabled: bool
    critical_manual_only: bool = True
    hosted_ai_allowed: bool = False
    llm_enabled_providers: list[Literal["gemini", "ollama"]] = []
    llm_models: list[LLMModelBindingInput] = []
    llm_fallback_allowed: bool = False
    allowed_agent_types: list[str] = ["TEMPERATURE", "INVENTORY", "LOT", "SUPPLIER", "HISTORY", "TRANSACTION"]
    blocked_categories: list[str] = ["RESTRICTED"]
    max_agent_iterations: int
    max_tool_calls: int
    parallelism: int
    timeout_seconds: int
    token_budget: int
    cost_budget_usd: float
    gemini_concurrency: int
    gemini_rate_limit: int
    gemini_timeout_seconds: int
    provider_concurrency: int
    provider_timeout_seconds: int
    structured_output_retry: int
    auto_investigation: bool
    auto_rca_draft: bool
    auto_capa_draft: bool
    auto_execute: bool
    approval_policy_by_risk: RiskApprovalInput
    required_roles: list[str]
    separation_of_duties: bool
    critical_approver_count: int
    tenant_queue_concurrency: int
    priority_policy: Literal["STRICT_PRIORITY"]
    retry_limit: int
    backoff_seconds: int
    allowed_tools: list[str]
    verification_window_hours: int


class UpdateConfigRequest(StrictModel):
    expected_version: int = Field(ge=0)
    config: RuntimeConfigInput
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value):
        if not value.strip():
            raise ValueError("설정 변경 사유를 입력해 주세요.")
        return value.strip()


class RollbackConfigRequest(StrictModel):
    target_version: int = Field(ge=1)
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=1000)

    _reason = field_validator("reason")(UpdateConfigRequest.reason_not_blank.__func__)


class CurrentRawConfig(RuntimeConfigInput):
    version: int = Field(ge=0)


class Permission(BaseModel):
    allowed: bool
    reason: str


class ConfigRule(BaseModel):
    min: float
    max: float
    integer: bool


class CurrentMetadata(BaseModel):
    created_at: str | None
    created_by: str | None
    reason: str
    parent_version: int | None


class RuntimeWorkspaceResponse(BaseModel):
    config: CurrentRawConfig
    effective: RuntimeConfigInput
    sources: dict[str, Literal["TENANT", "PLATFORM_DEFAULT"]]
    adjusted_fields: list[str]
    current: CurrentMetadata
    runtime_status: Literal["NOT_CONNECTED"]
    rules: dict[str, ConfigRule]
    save_permission: Permission
    rollback_permission: Permission
    scope: Literal["TENANT"]


class ConfigChange(BaseModel):
    field: str
    before: str
    after: str


class ConfigRevisionResponse(BaseModel):
    version: int
    parent_version: int | None
    rollback_source: int | None
    created_at: str
    actor: str
    reason: str
    changes: list[ConfigChange]
    compared_to_version: int
    rollback_changes: list[ConfigChange]
    snapshot: RuntimeConfigInput


class RuntimeHistoryResponse(BaseModel):
    revisions: list[ConfigRevisionResponse]
    limit: int
    offset: int
    has_more: bool
