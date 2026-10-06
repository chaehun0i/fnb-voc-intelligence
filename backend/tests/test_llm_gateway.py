"""FakeProvider가 안정된 응답과 오류 경계를 따르는지 검증합니다."""
import asyncio

import pytest

from src.ai.intelligence.models import LLMError, LLMErrorCode
from src.ai.intelligence.providers.fake import FakeProvider
from src.ai.intelligence.service import LLMGateway
from tests.test_llm_contracts import intent


def test_fake_success():
    result = asyncio.run(LLMGateway(FakeProvider()).execute(intent(), model="fake-v1"))
    assert result.provider == "fake" and result.usage.total_tokens == 15
    assert result.config_version == 1


@pytest.mark.parametrize("code", [LLMErrorCode.PROVIDER_TEMPORARY, LLMErrorCode.RATE_LIMITED, LLMErrorCode.TIMEOUT])
def test_normalized_errors(code):
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(FakeProvider([LLMError(code)])).execute(intent(), model="fake-v1"))
    assert error.value.code == code


def test_exception_message_is_not_exposed():
    with pytest.raises(LLMError) as error:
        asyncio.run(LLMGateway(FakeProvider([RuntimeError("SECRET")])).execute(intent(), model="fake-v1"))
    assert "SECRET" not in str(error.value)
