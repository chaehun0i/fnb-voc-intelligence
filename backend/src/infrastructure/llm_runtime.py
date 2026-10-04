"""명시적으로 구성한 Application만 Provider를 호출하며 startup에서는 호출하지 않습니다."""
from src.application.llm.service import LLMApplication
from src.llm.execution import RoutedLLMExecutor
from src.llm.providers.gemini import GeminiProvider
from src.llm.providers.ollama import OllamaProvider
from src.llm.router import ProviderRouter


def configured_llm_application(persistence):
    router = ProviderRouter({"gemini": GeminiProvider(), "ollama": OllamaProvider()})
    return LLMApplication(persistence, lambda recorder: RoutedLLMExecutor(router, recorder=recorder))
