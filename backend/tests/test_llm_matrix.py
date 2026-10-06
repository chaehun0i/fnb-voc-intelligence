"""정책·Provider·예산·deadline·fallback의 외부 네트워크 없는 회귀 행렬입니다."""
import ast
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.ai.intelligence.models import (
    LLMError,
    LLMErrorCode,
    LLMUsage,
    ProviderCapability,
    ProviderResponse,
)
from src.ai.intelligence.providers.fake import FakeProvider
from src.ai.intelligence.providers.ollama import OllamaProvider
from src.ai.intelligence.service import (
    LLMGateway,
    ProviderRouter,
    RoutedLLMExecutor,
    evaluate_policy,
)
from src.domain.config.resolution import ConfigResolver
from tests.test_llm_contracts import intent
from tests.test_llm_gemini import request
from tests.test_llm_router import configured


@pytest.mark.parametrize("classification", ["PUBLIC", "INTERNAL", "CONFIDENTIAL", "PII"])
def test_allowed_policy(classification):
    result = evaluate_policy(intent(classification=classification, free_text_reviewed=True), FakeProvider.capability)
    assert result.result == "ALLOW"


@pytest.mark.parametrize("field", ["customer_name", "phone", "email", "address", "external_customer_id", "api_key", "secret", "password", "raw_voc"])
def test_canonical_pii_absent(field):
    result = evaluate_policy(intent(payload_json=json.dumps({field: "PII-SENTINEL", "count": 1})), FakeProvider.capability)
    assert "PII-SENTINEL" not in result.payload_json and result.redacted


@pytest.mark.parametrize("code", [LLMErrorCode.POLICY_DENIED, LLMErrorCode.INVALID_REQUEST,
    LLMErrorCode.CAPABILITY_UNSUPPORTED, LLMErrorCode.OUTPUT_SCHEMA_INVALID, LLMErrorCode.OUTPUT_DOMAIN_INVALID])
def test_nonretryable_failure(code):
    provider = FakeProvider([LLMError(code)])
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(intent(), model="fake", retry_limit=1))
    assert error.value.code == code and provider.call_count == 1


def test_deadline_and_budget_prevent_new_request():
    for value, code in [(intent(deadline=datetime(2020, 1, 1, tzinfo=UTC)), LLMErrorCode.DEADLINE_EXHAUSTED),
        (intent(token_budget=1), LLMErrorCode.BUDGET_EXHAUSTED)]:
        provider = FakeProvider()
        with pytest.raises(LLMError) as error:
            asyncio.run(LLMGateway(provider).execute(value, model="fake"))
        assert error.value.code == code and provider.call_count == 0


def test_actual_async_timeout_is_bounded():
    provider = Mock(capability=FakeProvider.capability)
    async def never(_):
        await asyncio.Event().wait()
    provider.generate = never
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(intent(), model="fake", timeout_seconds=0.01))
    assert error.value.code == LLMErrorCode.TIMEOUT


def pair(primary_error, config_changes=None, fallback_capability=None):
    primary = Mock(capability=ProviderCapability(provider="gemini", hosted=True))
    primary.generate = AsyncMock(side_effect=LLMError(primary_error))
    alternative = Mock(capability=fallback_capability or ProviderCapability(provider="ollama", hosted=False))
    alternative.generate = AsyncMock(return_value=ProviderResponse(content='{"summary":"완료"}', usage=LLMUsage(input_tokens=10, output_tokens=5), finish_reason="STOP"))
    config = configured(llm_fallback_allowed=True, **(config_changes or {}))
    return primary, alternative, ConfigResolver().resolve(config)


def test_safe_fallback_and_usage_lineage():
    primary, alternative, resolved = pair(LLMErrorCode.PROVIDER_TEMPORARY)
    records = []
    result = asyncio.run(RoutedLLMExecutor(ProviderRouter({"gemini": primary, "ollama": alternative}), recorder=records.append).execute(intent(fallback_allowed=True), resolved))
    assert primary.generate.call_count == 2 and alternative.generate.call_count == 1
    assert result.fallback_used and result.provider == "ollama" and result.config_version == 1
    assert len(records) == 3 and records[-1].fallback


@pytest.mark.parametrize("error", [LLMErrorCode.INVALID_REQUEST, LLMErrorCode.POLICY_DENIED, LLMErrorCode.OUTPUT_SCHEMA_INVALID])
def test_fallback_is_not_for_permanent_failure(error):
    primary, alternative, resolved = pair(error)
    with pytest.raises(LLMError):
        asyncio.run(RoutedLLMExecutor(ProviderRouter({"gemini": primary, "ollama": alternative})).execute(intent(fallback_allowed=True), resolved))
    alternative.generate.assert_not_called()


def test_fallback_permission_capability_and_shared_budget():
    primary, alternative, resolved = pair(LLMErrorCode.PROVIDER_TEMPORARY)
    with pytest.raises(LLMError):
        asyncio.run(RoutedLLMExecutor(ProviderRouter({"gemini": primary, "ollama": alternative})).execute(intent(fallback_allowed=False), resolved))
    alternative.generate.assert_not_called()
    primary, alternative, resolved = pair(LLMErrorCode.PROVIDER_TEMPORARY, fallback_capability=ProviderCapability(provider="ollama", hosted=False, structured_output=False))
    with pytest.raises(LLMError) as error:
        asyncio.run(RoutedLLMExecutor(ProviderRouter({"gemini": primary, "ollama": alternative})).execute(intent(fallback_allowed=True), resolved))
    assert error.value.code == LLMErrorCode.CAPABILITY_UNSUPPORTED
    alternative.generate.assert_not_called()
    primary, alternative, resolved = pair(LLMErrorCode.PROVIDER_TEMPORARY)
    with pytest.raises(LLMError) as error:
        asyncio.run(RoutedLLMExecutor(ProviderRouter({"gemini": primary, "ollama": alternative})).execute(intent(fallback_allowed=True, token_budget=1500), resolved))
    assert error.value.code == LLMErrorCode.BUDGET_EXHAUSTED
    alternative.generate.assert_not_called()


def test_ollama_unavailable_without_network():
    def unavailable(req):
        raise httpx.ConnectError("SECRET", request=req)
    with pytest.raises(LLMError) as error:
        asyncio.run(OllamaProvider(transport=httpx.MockTransport(unavailable)).generate(request()))
    assert error.value.code == LLMErrorCode.PROVIDER_UNAVAILABLE


def test_sdk_does_not_leak_into_domain_application_or_jev():
    root = Path(__file__).parents[1] / "src"
    for directory in ("domain", "application", "ai"):
        for path in (root / directory).rglob("*.py"):
            if path.parent == root / "ai" / "intelligence" / "providers":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.Import):
                    assert all(not item.name.startswith(("google", "ollama")) for item in node.names), path
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith(("google", "ollama")), path


def test_domain_invalid_is_observed_without_response_text():
    records = []
    def invalid(_):
        raise ValueError("민감한 검증 원문")
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(FakeProvider(), recorder=records.append).execute(intent(), model="fake", domain_validator=invalid))
    assert error.value.code == LLMErrorCode.OUTPUT_DOMAIN_INVALID
    assert records[0].error_code == "OUTPUT_DOMAIN_INVALID" and "민감한 검증 원문" not in str(records)


def test_non_json_number_and_dynamic_external_ref_are_invalid():
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(FakeProvider(['{"summary":NaN}'])).execute(intent(output_schema_json='{"type":"object","properties":{"summary":{"type":["number","null"]}}}'), model="fake"))
    assert error.value.code == LLMErrorCode.OUTPUT_SCHEMA_INVALID
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(FakeProvider()).execute(intent(output_schema_json='{"$dynamicRef":"https://example.com/schema"}'), model="fake"))
    assert error.value.code == LLMErrorCode.INVALID_REQUEST


def test_schema_valid_unknown_evidence_is_business_invalid():
    provider = FakeProvider(['{"evidence_ids":["unknown"]}'])
    value = intent(input_references=("known",), output_schema_json='{"type":"object","properties":{"evidence_ids":{"type":"array","items":{"type":"string"}}},"required":["evidence_ids"]}')
    def validate_evidence(output):
        if not set(output["evidence_ids"]) <= set(value.input_references):
            raise ValueError("알 수 없는 근거 참조입니다.")
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(value, model="fake", repair_limit=1, domain_validator=validate_evidence))
    assert error.value.code == LLMErrorCode.OUTPUT_DOMAIN_INVALID and provider.call_count == 1
