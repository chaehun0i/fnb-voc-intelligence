"""Bounded-memory record iteration for large external files."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from .models import RawRecord


def iter_record_chunks(
    path: Path, kind: str, source: str, chunk_size: int
) -> Iterator[list[RawRecord]]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    if kind == "csv":
        with path.open(encoding="utf-8", newline="") as file:
            rows = csv.DictReader(file)
            yield from _chunk_rows(rows, source, chunk_size)
    elif kind == "jsonl":
        with path.open(encoding="utf-8") as file:
            rows = (json.loads(line) for line in file if line.strip())
            yield from _chunk_rows(rows, source, chunk_size)
    else:
        raise ValueError("chunked ingestion supports csv and jsonl")


def _chunk_rows(rows: object, source: str, chunk_size: int) -> Iterator[list[RawRecord]]:
    chunk: list[RawRecord] = []
    for row_number, row in enumerate(rows, start=2):
        chunk.append(RawRecord(external_id=str(row.get("id")) if row.get("id") else None, values=row, source=source, row_number=row_number))
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
