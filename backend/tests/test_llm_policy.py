"""PII 최소화와 hosted 정책은 실제 호출보다 먼저 강제됩니다."""
import asyncio
import json

import pytest

from src.llm.contracts import ProviderCapability
from src.llm.data_policy import evaluate_policy
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.gateway import LLMGateway
from src.llm.providers.fake import FakeProvider
from tests.test_llm_contracts import intent


def test_recursive_redaction():
    value = intent(classification="PII", free_text_reviewed=True, payload_json=json.dumps({"count": 1,
        "customer_name": "SECRET", "nested": [{"email": "a@example.com", "safe": 2}], "api_key": "KEY"}))
    result = evaluate_policy(value, FakeProvider.capability)
    assert result.redacted
    assert json.loads(result.payload_json) == {"count": 1, "nested": [{"safe": 2}]}


@pytest.mark.parametrize("classification,hosted,allowed,reviewed", [("RESTRICTED", True, True, True),
    ("RESTRICTED", False, False, True), ("INTERNAL", True, False, True), ("PII", False, False, False)])
def test_policy_denied_before_provider(classification, hosted, allowed, reviewed):
    provider = FakeProvider()
    provider.capability = ProviderCapability(provider="fake", hosted=hosted)
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(intent(classification=classification, free_text_reviewed=reviewed),
            model="fake", hosted_ai_allowed=allowed))
    assert error.value.code == LLMErrorCode.POLICY_DENIED
    assert provider.call_count == 0
