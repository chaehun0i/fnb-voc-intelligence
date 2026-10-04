"""로컬 최초 실행 설정이며 저장된 Tenant Config를 대신하지 않습니다."""
import os

from src.domain.config.models import LLMModelBinding, RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed
from src.llm.errors import LLMError, LLMErrorCode


def local_llm_config(environ=None):
    """명시적으로 켠 로컬 환경만 Gemini를 허용합니다. 키는 설정에 넣지 않습니다."""
    values = os.environ if environ is None else environ
    if values.get("SERVIQ_LLM_ENABLED", "false").lower() != "true":
        return RuntimeConfig()
    if values.get("APP_ENV", "local") not in {"local", "development"}:
        raise LLMError(LLMErrorCode.POLICY_DENIED)
    model = values.get("MODEL", "").strip()
    if not model:
        raise LLMError(LLMErrorCode.PROVIDER_NOT_CONFIGURED)
    try:
        # 공식 청구 단가가 아니라 로컬 테스트의 보수적인 예산 예약 단가입니다.
        input_rate = float(values.get("LLM_INPUT_USD_PER_MILLION", "10"))
        output_rate = float(values.get("LLM_OUTPUT_USD_PER_MILLION", "100"))
        config = RuntimeConfig(hosted_ai_allowed=True, llm_enabled_providers=("gemini",),
            llm_models=tuple(LLMModelBinding("gemini", model_class, model, input_rate, output_rate)
                for model_class in ("FAST", "STANDARD", "REASONING")), llm_fallback_allowed=False)
        return ConfigResolver().resolve(config).effective
    except (ValueError, TypeError, ConfigValidationFailed):
        raise LLMError(LLMErrorCode.INVALID_REQUEST) from None
