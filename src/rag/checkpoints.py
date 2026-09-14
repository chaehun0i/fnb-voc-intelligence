"""Persistent checkpoints for safely resuming ordered batch jobs."""

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from .batching import iter_batches


@dataclass(frozen=True)
class JobCheckpoint:
    completed_batches: int = 0
    processed: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0


class CheckpointStore(Protocol):
    def load(self) -> JobCheckpoint: ...

    def save(self, checkpoint: JobCheckpoint) -> None: ...


class JsonCheckpointStore:
    """A small JSON checkpoint store suitable for a single local job."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> JobCheckpoint:
        if not self.path.exists():
            return JobCheckpoint()
        return JobCheckpoint(**json.loads(self.path.read_text(encoding="utf-8")))

    def save(self, checkpoint: JobCheckpoint) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(checkpoint)), encoding="utf-8")


def execute_with_checkpoint[Item](
    items: Iterable[Item],
    batch_size: int,
    process: Callable[[list[Item]], JobCheckpoint],
    store: CheckpointStore,
) -> JobCheckpoint:
    """Resume after saved batches and persist state only after each success."""
    checkpoint = store.load()
    for batch_number, batch in enumerate(iter_batches(items, batch_size), start=1):
        if batch_number <= checkpoint.completed_batches:
            continue
        result = process(batch)
        checkpoint = JobCheckpoint(
            completed_batches=batch_number,
            processed=result.processed,
            succeeded=result.succeeded,
            skipped=result.skipped,
            failed=result.failed,
        )
        store.save(checkpoint)
    return checkpoint
