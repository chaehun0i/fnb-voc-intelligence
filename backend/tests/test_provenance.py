from datetime import UTC, datetime

from src.ingestion.provenance import IngestionRun, save_ingestion_run


class Cursor:
    def __init__(self) -> None: self.calls = []
    def execute(self, query: str, params: tuple[object, ...]) -> None: self.calls.append((query, params))


def test_ingestion_run_is_saved() -> None:
    cursor = Cursor()
    run = IngestionRun("run", "partner", datetime(2026, 9, 15, tzinfo=UTC), None, 1, 1, 0, 0, {})
    save_ingestion_run(cursor, run)
    assert "ON CONFLICT" in cursor.calls[0][0]
