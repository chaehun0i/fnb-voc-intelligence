"""구조화 응답 repair는 한 번이며 업무 검증 실패는 repair하지 않습니다."""
import asyncio

import pytest

from src.ai.intelligence.models import LLMError, LLMErrorCode
from src.ai.intelligence.providers.fake import FakeProvider
from src.ai.intelligence.service import LLMGateway
from tests.test_llm_contracts import intent


@pytest.mark.parametrize("responses,success,calls", [(['{"summary":"정상"}'], True, 1),
    (["broken", '{"summary":"복구"}'], True, 2),
    (["{}", "{}", '{"summary":"호출 금지"}'], False, 2)])
def test_structured_repair(responses, success, calls):
    provider = FakeProvider(responses)
    if success:
        result = asyncio.run(LLMGateway(provider).execute(intent(), model="fake", repair_limit=10))
        assert result.structured_retry_count == calls - 1
        assert result.usage.total_tokens == 15 * calls
    else:
        with pytest.raises(LLMError) as error:
            asyncio.run(LLMGateway(provider).execute(intent(), model="fake", repair_limit=10))
        assert error.value.code == LLMErrorCode.OUTPUT_SCHEMA_INVALID
    assert provider.call_count == calls


def test_business_validation_is_separate():
    def evidence_check(value):
        if value["summary"] != "known-evidence":
            raise ValueError("존재하지 않는 근거")
    provider = FakeProvider()
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(intent(), model="fake", repair_limit=1, domain_validator=evidence_check))
    assert error.value.code == LLMErrorCode.OUTPUT_DOMAIN_INVALID
    assert provider.call_count == 1


def test_remote_schema_ref_never_calls_provider():
    provider = FakeProvider()
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider).execute(intent(output_schema_json='{"$ref":"https://example.com/schema"}'), model="fake"))
    assert error.value.code == LLMErrorCode.INVALID_REQUEST and provider.call_count == 0
