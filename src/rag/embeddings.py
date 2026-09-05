"""Provider-neutral text embedding boundary and deterministic test provider."""

from collections.abc import Sequence
from hashlib import sha256
from math import sqrt
from typing import Protocol


class EmbeddingUnavailableError(RuntimeError):
    """Raised when an embedding provider is temporarily unavailable."""


class EmbeddingProvider(Protocol):
    """Minimal interface required by indexing and semantic search services."""

    @property
    def model(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    """Generate stable normalized vectors without network or model dependencies."""

    def __init__(self, dimension: int = 8, model: str = "fake-v1") -> None:
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self._dimension = dimension
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        values = []
        for index in range(self.dimension):
            digest = sha256(f"{index}\0{text}".encode()).digest()
            integer = int.from_bytes(digest[:8], "big")
            values.append((integer / (2**64 - 1)) * 2 - 1)
        magnitude = sqrt(sum(value * value for value in values)) or 1.0
        return [value / magnitude for value in values]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]
