"""Provider-neutral text generation boundary and deterministic fake."""

from hashlib import sha256
from typing import Protocol


class TextGenerator(Protocol):
    @property
    def model(self) -> str: ...

    def generate(self, prompt: str) -> str: ...


class FakeTextGenerator:
    def __init__(self, model: str = "fake-v1", response: str | None = None) -> None:
        self._model = model
        self.response = response
        self.prompts: list[str] = []

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.response is not None:
            return self.response
        digest = sha256(prompt.encode("utf-8")).hexdigest()[:12]
        return f"fake-answer:{digest}"
