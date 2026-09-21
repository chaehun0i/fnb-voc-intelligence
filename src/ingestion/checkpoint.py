"""Persistent chunk checkpoints for resumable ingestion."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestionCheckpoint:
    completed_chunk: int = 0
    accepted: int = 0
    rejected: int = 0


class FileCheckpoint:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> IngestionCheckpoint:
        return IngestionCheckpoint(**json.loads(self.path.read_text())) if self.path.exists() else IngestionCheckpoint()

    def save(self, checkpoint: IngestionCheckpoint) -> None:
        self.path.write_text(json.dumps(asdict(checkpoint)), encoding="utf-8")
