"""Config mapping과 정책/capability를 실제 Provider 선택 전에 검증합니다."""
from dataclasses import replace
from unittest.mock import Mock

import pytest

from src.domain.config.models import (
    LLMModelBinding,
    RuntimeConfig,
    config_document,
    config_from_document,
)
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed
from src.llm.contracts import ProviderCapability
from src.llm.errors import LLMError, LLMErrorCode
from src.llm.router import ProviderRouter
from tests.test_llm_contracts import intent


def configured(**changes):
    base = replace(RuntimeConfig(), hosted_ai_allowed=True, llm_enabled_providers=("gemini", "ollama"),
        llm_models=tuple(LLMModelBinding(p, c, f"configured-{c}", 1, 2) for p in ("gemini", "ollama") for c in ("FAST", "STANDARD", "REASONING")))
    return replace(base, **changes)


@pytest.mark.parametrize("model_class", ["FAST", "STANDARD", "REASONING"])
def test_config_mapping(model_class):
    provider = Mock(capability=ProviderCapability(provider="gemini", hosted=True))
    selection = ProviderRouter({"gemini": provider}).select(intent(model_class=model_class), ConfigResolver().resolve(configured()))
    assert selection.binding.model == f"configured-{model_class}"


def test_old_config_is_disabled_and_roundtrip_is_immutable():
    config = config_from_document(config_document(RuntimeConfig()))
    assert config.llm_models == () and config.llm_enabled_providers == ()
    assert config_from_document(config_document(configured())) == configured()
    with pytest.raises(LLMError) as error:
        ProviderRouter({}).select(intent(), ConfigResolver().resolve(config))
    assert error.value.code == LLMErrorCode.PROVIDER_NOT_CONFIGURED


def test_capability_and_model_validation():
    provider = Mock(capability=ProviderCapability(provider="gemini", hosted=True, structured_output=False))
    with pytest.raises(LLMError) as error:
        ProviderRouter({"gemini": provider}).select(intent(), ConfigResolver().resolve(configured()))
    assert error.value.code == LLMErrorCode.CAPABILITY_UNSUPPORTED
    with pytest.raises(ConfigValidationFailed):
        ConfigResolver().resolve(configured(llm_models=(LLMModelBinding("gemini", "FAST", "", 1, 2),)))
