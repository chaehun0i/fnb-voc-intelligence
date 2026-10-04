"""모델명은 versioned Config에서만 읽고 선택마다 정책과 capability를 검증합니다."""
from dataclasses import dataclass

from src.llm.data_policy import evaluate_policy
from src.llm.errors import LLMError, LLMErrorCode


@dataclass(frozen=True)
class ProviderSelection:
    provider: object
    binding: object
    timeout_seconds: float


class ProviderRouter:
    def __init__(self, providers):
        self.providers = dict(providers)

    def select(self, intent, resolved, *, fallback=False):
        config = resolved.effective
        if fallback and not (intent.fallback_allowed and config.llm_fallback_allowed):
            raise LLMError(LLMErrorCode.POLICY_DENIED)
        name = config.fallback_llm_provider if fallback else config.default_llm_provider
        if name not in config.llm_enabled_providers or name not in self.providers:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        provider = self.providers[name]
        capability = provider.capability
        if capability.provider != name or not capability.structured_output or intent.model_class not in capability.model_classes:
            raise LLMError(LLMErrorCode.CAPABILITY_UNSUPPORTED)
        binding = next((item for item in config.llm_models if item.provider == name and item.model_class == intent.model_class), None)
        if binding is None:
            raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
        evaluate_policy(intent, capability, hosted_ai_allowed=config.hosted_ai_allowed)
        # 안전한 상한 추정: UTF-8 바이트 수는 입력 토큰보다 보수적인 예약량입니다.
        input_bound = len(intent.payload_json.encode("utf-8")) + len(intent.output_schema_json.encode("utf-8")) + 256
        output_bound = intent.max_output_tokens
        cost = (input_bound * binding.input_usd_per_million + output_bound * binding.output_usd_per_million) / 1_000_000
        if (input_bound + output_bound > min(intent.token_budget, config.token_budget, capability.context_limit)
                or cost > min(intent.cost_budget_usd, config.cost_budget_usd)):
            raise LLMError(LLMErrorCode.BUDGET_EXHAUSTED)
        timeout = config.provider_timeout_seconds
        if name == "gemini":
            timeout = min(timeout, config.gemini_timeout_seconds)
        return ProviderSelection(provider, binding, timeout)
