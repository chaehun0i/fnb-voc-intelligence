"""Provider 원문 대신 안전한 코드만 외부 경계에 전달합니다."""
from enum import StrEnum


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
