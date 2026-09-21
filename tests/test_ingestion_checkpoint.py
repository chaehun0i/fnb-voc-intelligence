from pathlib import Path

from src.ingestion.checkpoint import FileCheckpoint, IngestionCheckpoint


def test_checkpoint_round_trip_resumes_completed_chunk(tmp_path: Path) -> None:
    store = FileCheckpoint(tmp_path / "checkpoint.json")
    store.save(IngestionCheckpoint(completed_chunk=2, accepted=10))
    assert store.load() == IngestionCheckpoint(completed_chunk=2, accepted=10)
