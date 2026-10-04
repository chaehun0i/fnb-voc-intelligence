"""Provider 호출 전 canonical PII를 최소화하는 보수적 전송 정책입니다."""
import json
from dataclasses import dataclass, field
from enum import StrEnum

from src.llm.contracts import DataClassification
from src.llm.errors import LLMError, LLMErrorCode

PII_FIELDS = frozenset({"customer_name", "phone", "email", "address", "external_customer_id"})
FORBIDDEN_FIELDS = frozenset({"api_key", "secret", "password", "credential", "raw_voc", "raw_document"})


class PolicyResult(StrEnum):
    ALLOW = "ALLOW"
    ALLOW_REDACTED = "ALLOW_REDACTED"
    DENY = "DENY"
    HUMAN_ONLY = "HUMAN_ONLY"


@dataclass(frozen=True)
class PolicyDecision:
    result: PolicyResult
    payload_json: str = field(repr=False)
    redacted: bool


def minimize(value):
    redacted = False
    if isinstance(value, dict):
        output = {}
        for key, item in value.items():
            normalized = key.lower()
            if normalized in PII_FIELDS | FORBIDDEN_FIELDS:
                redacted = True
                continue
            cleaned, changed = minimize(item)
            output[key] = cleaned
            redacted |= changed
        return output, redacted
    if isinstance(value, list):
        pairs = [minimize(item) for item in value]
        return [item for item, _ in pairs], any(changed for _, changed in pairs)
    return value, False


def evaluate_policy(intent, capability, *, hosted_ai_allowed=False):
    if intent.classification == DataClassification.RESTRICTED:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    if capability.hosted and not hosted_ai_allowed:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    # 자유 텍스트의 PII 여부는 이 redactor가 보장하지 않습니다. Application 검토가 필요합니다.
    if intent.classification in {DataClassification.PII, DataClassification.CONFIDENTIAL} and not intent.free_text_reviewed:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    payload, redacted = minimize(json.loads(intent.payload_json))
    if not payload:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    return PolicyDecision(PolicyResult.ALLOW_REDACTED if redacted else PolicyResult.ALLOW,
        json.dumps(payload, sort_keys=True, ensure_ascii=False), redacted)
