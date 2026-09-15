"""Auditable ingestion run persistence."""

from dataclasses import dataclass
from datetime import datetime

INGESTION_RUNS_SQL = """CREATE TABLE IF NOT EXISTS ingestion_runs (
run_id TEXT PRIMARY KEY, source TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL,
completed_at TIMESTAMPTZ, input_count INTEGER NOT NULL, accepted_count INTEGER NOT NULL,
rejected_count INTEGER NOT NULL, duplicate_count INTEGER NOT NULL, metadata JSONB NOT NULL)"""


@dataclass(frozen=True)
class IngestionRun:
    run_id: str
    source: str
    started_at: datetime
    completed_at: datetime | None
    input_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    metadata: dict[str, str]


def save_ingestion_run(cursor: object, run: IngestionRun) -> None:
    cursor.execute("INSERT INTO ingestion_runs VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO UPDATE SET completed_at=EXCLUDED.completed_at", (run.run_id, run.source, run.started_at, run.completed_at, run.input_count, run.accepted_count, run.rejected_count, run.duplicate_count, run.metadata))  # type: ignore[attr-defined]
