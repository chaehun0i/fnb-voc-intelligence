"""설정은 서버 상한과 승인 안전 규칙 안에서만 해석합니다."""
import math
from dataclasses import fields

from src.domain.config.models import ResolvedConfig, RuntimeConfig

# 실제 Runtime 적용 전에도 저장 입력을 제한합니다. 기존 Worker 정책은 변경하지 않습니다.
DEFAULT_RULES = {
    "max_agent_iterations": (1, 20, True), "max_tool_calls": (1, 50, True),
    "parallelism": (1, 10, True), "timeout_seconds": (5, 600, True),
    "token_budget": (100, 100000, True), "cost_budget_usd": (0.01, 20, False),
    "gemini_concurrency": (1, 10, True), "gemini_rate_limit": (1, 300, True),
    "gemini_timeout_seconds": (5, 300, True), "structured_output_retry": (0, 3, True),
    "provider_concurrency": (1, 10, True), "provider_timeout_seconds": (5, 300, True),
    "tenant_queue_concurrency": (1, 10, True), "retry_limit": (0, 10, True),
    "backoff_seconds": (1, 60, True), "critical_approver_count": (2, 5, True),
    "verification_window_hours": (1, 168, True),
}
RESERVED_READ_TOOLS = frozenset({"incident.get", "voc.search", "inventory.snapshot", "transaction.search"})


class ConfigValidationFailed(Exception):
    def __init__(self, details):
        self.details = details
        super().__init__("CONFIG_VALIDATION_FAILED")


class ConfigResolver:
    def __init__(self, rules=None, allowed_tools=None):
        self.rules = dict(DEFAULT_RULES if rules is None else rules)
        self.allowed_tools = RESERVED_READ_TOOLS if allowed_tools is None else frozenset(allowed_tools)

    def resolve(self, config: RuntimeConfig, *, source="TENANT") -> ResolvedConfig:
        errors = []
        for key, (minimum, maximum, integer) in self.rules.items():
            value = getattr(config, key)
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not minimum <= value <= maximum or (integer and type(value) is not int)):
                errors.append({"field": key, "type": "SAFETY_CAP", "reason": f"{minimum}~{maximum} 범위의 {'정수' if integer else '숫자'}가 필요합니다."})
        for item in fields(config):
            if type(item.default) is bool and type(getattr(config, item.name)) is not bool:
                errors.append({"field": item.name, "type": "BOOLEAN", "reason": "사용 여부는 boolean이어야 합니다."})
        for risk in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            value = getattr(config.approval_policy_by_risk, risk)
            if type(value) is not bool or (risk in {"HIGH", "CRITICAL"} and not value):
                errors.append({"field": "approval_policy_by_risk." + risk, "type": "APPROVAL_SAFETY", "reason": "높음·긴급 위험의 사람 승인은 해제할 수 없습니다."})
        if config.separation_of_duties is not True:
            errors.append({"field": "separation_of_duties", "type": "APPROVAL_SAFETY", "reason": "요청자와 승인자 분리 계약을 유지해야 합니다."})
        if (not config.required_roles or len(set(config.required_roles)) != len(config.required_roles)
                or not set(config.required_roles) <= {"HQ_ADMIN", "REVIEWER"}):
            errors.append({"field": "required_roles", "type": "APPROVAL_SAFETY", "reason": "승인 역할은 HQ_ADMIN/REVIEWER 중 하나 이상이어야 합니다."})
        if (len(config.allowed_tools) != len(set(config.allowed_tools))
                or not set(config.allowed_tools) <= self.allowed_tools):
            errors.append({"field": "allowed_tools", "type": "TOOL_NOT_ALLOWED", "reason": "시스템이 예약한 읽기 도구만 설정할 수 있습니다."})
        for key in ("default_llm_provider", "fallback_llm_provider"):
            if getattr(config, key) not in {"gemini", "ollama"}:
                errors.append({"field": key, "type": "PROVIDER", "reason": "Gemini 또는 Ollama를 선택해 주세요."})
        if config.priority_policy != "STRICT_PRIORITY":
            errors.append({"field": "priority_policy", "type": "PRIORITY_POLICY", "reason": "현재는 우선순위 순서 정책만 지원합니다."})
        for key, choices in (("allowed_agent_types", {"TEMPERATURE", "INVENTORY", "LOT", "SUPPLIER", "HISTORY", "TRANSACTION"}),
                             ("blocked_categories", {"COLD_CHAIN", "FOOD_SAFETY", "SUPPLIER_LOT", "TRANSACTION", "GENERAL", "UNKNOWN", "RESTRICTED"})):
            values = getattr(config, key)
            if len(set(values)) != len(values) or not set(values) <= choices:
                errors.append({"field": key, "type": "JEV_POLICY", "reason": "등록된 분류·조사 후보만 중복 없이 설정해 주세요."})
        if "RESTRICTED" not in config.blocked_categories:
            errors.append({"field": "blocked_categories", "type": "JEV_POLICY", "reason": "제한된 자료 분류는 자동 조사 차단을 유지해야 합니다."})
        if errors:
            raise ConfigValidationFailed(errors)
        # 초과 값을 조용히 clamp하지 않고 거부하므로 조정된 값은 없습니다.
        return ResolvedConfig(config, tuple((item.name, source) for item in fields(config)))

    def field_rules(self):
        return {key: {"min": value[0], "max": value[1], "integer": value[2]} for key, value in self.rules.items()}
