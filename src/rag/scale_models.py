"""Validated contracts for resumable scale jobs."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScaleJobConfig:
    batch_size: int = 100
    workers: int = 1
    retries: int = 2
    resume: bool = False
    limit: int | None = None

    def __post_init__(self) -> None:
        if self.batch_size < 1 or self.workers < 1 or self.retries < 0:
            raise ValueError("invalid scale job config")
        if self.limit is not None and self.limit < 1:
            raise ValueError("invalid scale job config")

@dataclass(frozen=True)
class ScaleJobResult:
    processed: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    elapsed_seconds: float = 0.0
