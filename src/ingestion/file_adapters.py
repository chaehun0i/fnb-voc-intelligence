"""CSV/JSON file adapters mapping external records into domain models."""

import csv
import json
from pathlib import Path

from pydantic import ValidationError

from src.data.models import Product, Review

from .models import RawRecord


def read_file(path: Path, kind: str, source: str, encoding: str = "utf-8") -> list[RawRecord]:
    text = path.read_text(encoding=encoding)
    if kind == "csv":
        rows = list(csv.DictReader(text.splitlines()))
    elif kind == "json":
        rows = json.loads(text)
    elif kind == "jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        raise ValueError(f"unsupported format: {kind}")
    return [RawRecord(external_id=str(row.get("id")) if row.get("id") else None, values=row, source=source, row_number=index) for index, row in enumerate(rows, 2)]


def map_product(record: RawRecord, mapping: dict[str, str]) -> Product:
    values = {field: record.values.get(column) for field, column in mapping.items()}
    values.setdefault("source", record.source)
    return Product.model_validate(values)


def map_review(record: RawRecord, mapping: dict[str, str]) -> Review:
    values = {field: record.values.get(column) for field, column in mapping.items()}
    values.setdefault("source", record.source)
    return Review.model_validate(values)


def errors_for(records: list[RawRecord], mapper: object, mapping: dict[str, str]) -> list[str]:
    errors = []
    for record in records:
        try:
            mapper(record, mapping)
        except ValidationError as error:
            errors.append(f"row {record.row_number}: {error.errors()[0]['msg']}")
    return errors
