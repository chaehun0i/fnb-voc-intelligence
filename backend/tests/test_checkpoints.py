from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.rag.checkpoints import (
    JobCheckpoint,
    JsonCheckpointStore,
    execute_with_checkpoint,
)


@dataclass
class MemoryStore:
    checkpoint: JobCheckpoint = field(default_factory=JobCheckpoint)

    def load(self) -> JobCheckpoint:
        return self.checkpoint

    def save(self, checkpoint: JobCheckpoint) -> None:
        self.checkpoint = checkpoint


def test_checkpoint_resumes_without_reprocessing_completed_batches() -> None:
    store = MemoryStore()
    processed: list[list[int]] = []

    def fail_on_second(batch: list[int]) -> JobCheckpoint:
        if batch == [3, 4]:
            raise RuntimeError("interrupted")
        processed.append(batch)
        return JobCheckpoint(processed=len(processed) * 2, succeeded=len(processed) * 2)

    with pytest.raises(RuntimeError, match="interrupted"):
        execute_with_checkpoint(range(1, 6), 2, fail_on_second, store)
    assert store.checkpoint.completed_batches == 1

    def finish(batch: list[int]) -> JobCheckpoint:
        processed.append(batch)
        count = sum(len(item) for item in processed)
        return JobCheckpoint(processed=count, succeeded=count)

    result = execute_with_checkpoint(range(1, 6), 2, finish, store)
    assert processed == [[1, 2], [3, 4], [5]]
    assert result.completed_batches == 3


def test_json_checkpoint_store_round_trips(tmp_path: Path) -> None:
    store = JsonCheckpointStore(tmp_path / "checkpoint.json")
    store.save(JobCheckpoint(completed_batches=2, processed=4, skipped=1))
    assert store.load() == JobCheckpoint(completed_batches=2, processed=4, skipped=1)
