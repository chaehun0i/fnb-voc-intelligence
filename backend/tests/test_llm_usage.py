"""제한 retry와 원문 없는 trace를 FakeProvider로 확인합니다."""
import asyncio
from dataclasses import asdict

import pytest

from src.llm.errors import LLMError, LLMErrorCode
from src.llm.gateway import LLMGateway
from src.llm.providers.fake import FakeProvider
from tests.test_llm_contracts import intent


def test_bounded_retry_and_safe_trace():
    records = []
    provider = FakeProvider([LLMError(LLMErrorCode.RATE_LIMITED), '{"summary":"응답 원문"}'])
    result = asyncio.run(LLMGateway(provider, recorder=records.append).execute(intent(payload_json='{"count":1,"email":"SECRET"}'), model="fake", retry_limit=99))
    assert provider.call_count == 2 and result.provider_retry_count == 1
    assert records[0].error_code == "RATE_LIMITED" and records[1].provider_retry
    assert records[1].redacted
    assert "SECRET" not in str([asdict(record) for record in records])
    assert "응답 원문" not in str(records)


def test_retry_is_bounded_and_trace_failure_is_not_retried():
    provider = FakeProvider([LLMError(LLMErrorCode.PROVIDER_TEMPORARY)] * 10)
    with pytest.raises(LLMError):
        asyncio.run(LLMGateway(provider).execute(intent(), model="fake", retry_limit=99))
    assert provider.call_count == 2
    def broken(_):
        raise RuntimeError("DB SECRET")
    provider = FakeProvider()
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(provider, recorder=broken).execute(intent(), model="fake", retry_limit=1))
    assert error.value.code == LLMErrorCode.TRACE_UNAVAILABLE and provider.call_count == 1
