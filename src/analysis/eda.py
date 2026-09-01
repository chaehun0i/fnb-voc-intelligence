"""Reusable, deterministic exploratory data analysis helpers."""

from collections import Counter
from statistics import mean, median, stdev
from typing import Any

from src.data.models import Product, Review


def dataset_summary(records: list[Product] | list[Review]) -> dict[str, Any]:
    """Return a stable schema summary for validated records."""
    if not records:
        return {"row_count": 0, "columns": [], "dtypes": {}, "null_counts": {}, "unique_counts": {}}
    rows = [record.model_dump() for record in records]
    columns = list(rows[0])
    return {"row_count": len(rows), "columns": columns, "dtypes": {column: type(rows[0][column]).__name__ for column in columns}, "null_counts": {column: sum(row[column] is None for row in rows) for column in columns}, "unique_counts": {column: len({row[column] for row in rows}) for column in columns}}


def rating_distribution(reviews: list[Review]) -> dict[str, Any]:
    counts = Counter(review.rating for review in reviews)
    total = len(reviews)
    ratings = [review.rating for review in reviews]
    return {"frequency": {rating: counts.get(rating, 0) for rating in range(1, 6)}, "percentage": {rating: counts.get(rating, 0) / total * 100 if total else 0 for rating in range(1, 6)}, "mean": mean(ratings) if ratings else None, "median": median(ratings) if ratings else None, "stdev": stdev(ratings) if len(ratings) > 1 else 0.0}
