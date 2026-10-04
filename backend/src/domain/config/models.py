"""HTTP·UI와 독립적인 운영 설정과 불변 버전 스냅샷입니다."""
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal

Provider = Literal["gemini", "ollama"]


@dataclass(frozen=True)
class RiskApproval:
    LOW: bool = False
    MEDIUM: bool = True
    HIGH: bool = True
    CRITICAL: bool = True


@dataclass(frozen=True)
class RuntimeConfig:
    default_llm_provider: Provider = "gemini"
    fallback_llm_provider: Provider = "ollama"
    jev_enabled: bool = False
    max_agent_iterations: int = 5
    max_tool_calls: int = 20
    parallelism: int = 3
    timeout_seconds: int = 120
    token_budget: int = 20000
    cost_budget_usd: float = 2.0
    gemini_concurrency: int = 3
    gemini_rate_limit: int = 60
    gemini_timeout_seconds: int = 60
    provider_concurrency: int = 3
    provider_timeout_seconds: int = 60
    structured_output_retry: int = 2
    auto_investigation: bool = False
    auto_rca_draft: bool = False
    auto_capa_draft: bool = False
    auto_execute: bool = False
    approval_policy_by_risk: RiskApproval = field(default_factory=RiskApproval)
    required_roles: tuple[str, ...] = ("REVIEWER", "HQ_ADMIN")
    separation_of_duties: bool = True
    critical_approver_count: int = 2
    tenant_queue_concurrency: int = 3
    priority_policy: Literal["STRICT_PRIORITY"] = "STRICT_PRIORITY"
    retry_limit: int = 3
    backoff_seconds: int = 2
    allowed_tools: tuple[str, ...] = ()
    verification_window_hours: int = 24

    def __post_init__(self):
        if not isinstance(self.approval_policy_by_risk, RiskApproval):
            raise TypeError("승인 정책은 불변 RiskApproval 타입이어야 합니다.")
        object.__setattr__(self, "required_roles", tuple(self.required_roles))
        object.__setattr__(self, "allowed_tools", tuple(self.allowed_tools))


@dataclass(frozen=True)
class ConfigVersion:
    config_version: int
    tenant_id: str
    config: RuntimeConfig
    reason: str
    created_by: str
    created_at: datetime
    parent_version: int | None = None
    rollback_source: int | None = None
    scope: Literal["TENANT"] = "TENANT"


@dataclass(frozen=True)
class ResolvedConfig:
    effective: RuntimeConfig
    sources: tuple[tuple[str, str], ...]
    adjusted_fields: tuple[str, ...] = ()
    runtime_status: str = "NOT_CONNECTED"


def config_document(config: RuntimeConfig) -> dict:
    document = asdict(config)
    for key in ("required_roles", "allowed_tools"):
        document[key] = list(document[key])
    return document


def config_from_document(document: dict) -> RuntimeConfig:
    values = dict(document)
    values["approval_policy_by_risk"] = RiskApproval(**values["approval_policy_by_risk"])
    for key in ("required_roles", "allowed_tools"):
        values[key] = tuple(values[key])
    return RuntimeConfig(**values)


def version_document(version: ConfigVersion) -> dict:
    return {**asdict(version), "created_at": version.created_at.isoformat()}


def version_from_document(document: dict) -> ConfigVersion:
    return ConfigVersion(**{**document, "config": config_from_document(document["config"]),
                            "created_at": datetime.fromisoformat(document["created_at"])})
