"""Reusable, deterministic exploratory data analysis helpers."""

from typing import Any

from src.data.models import Product, Review


def dataset_summary(records: list[Product] | list[Review]) -> dict[str, Any]:
    """Return a stable schema summary for validated records."""
    if not records:
        return {"row_count": 0, "columns": [], "dtypes": {}, "null_counts": {}, "unique_counts": {}}
    rows = [record.model_dump() for record in records]
    columns = list(rows[0])
    return {"row_count": len(rows), "columns": columns, "dtypes": {column: type(rows[0][column]).__name__ for column in columns}, "null_counts": {column: sum(row[column] is None for row in rows) for column in columns}, "unique_counts": {column: len({row[column] for row in rows}) for column in columns}}
