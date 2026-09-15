"""Deterministic source-to-load ingestion orchestration."""

from collections.abc import Callable

from .adapters import SourceAdapter
from .models import IngestionResult
from .normalize import deduplicate


def run_pipeline[Item](
    adapter: SourceAdapter,
    mapper: Callable[[object], Item],
    key: Callable[[Item], object],
    persist: Callable[[list[Item]], None] | None = None,
) -> tuple[list[Item], IngestionResult]:
    """Normalize valid source records and optionally persist unique items."""
    accepted: list[Item] = []
    errors: list[str] = []
    records = list(adapter.read())
    for record in records:
        try:
            accepted.append(mapper(adapter.normalize(record)))
        except (TypeError, ValueError) as error:
            errors.append(f"row {record.row_number}: {error}")
    unique, duplicates = deduplicate(accepted, key)
    if persist is not None:
        persist(unique)
    return unique, IngestionResult(input_count=len(records), accepted_count=len(unique), rejected_count=len(errors), duplicate_count=duplicates, errors=errors)
