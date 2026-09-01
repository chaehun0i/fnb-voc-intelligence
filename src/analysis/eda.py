"""Reusable, deterministic exploratory data analysis helpers."""

import re
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


def text_length_distribution(reviews: list[Review], buckets: tuple[int, ...] = (10, 30, 60)) -> dict[str, Any]:
    lengths = [len(review.review_text) for review in reviews]
    result = {f"<= {limit}": sum(length <= limit for length in lengths) for limit in buckets}
    result[f"> {buckets[-1]}"] = sum(length > buckets[-1] for length in lengths)
    return {"min": min(lengths, default=None), "max": max(lengths, default=None), "mean": mean(lengths) if lengths else None, "median": median(lengths) if lengths else None, "quartiles": [sorted(lengths)[int((len(lengths) - 1) * q)] for q in (0.25, 0.5, 0.75)] if lengths else [], "buckets": result}


def product_review_metrics(products: list[Product], reviews: list[Review]) -> list[dict[str, Any]]:
    """Aggregate review measures while preserving zero-review products."""
    output = []
    for product in products:
        items = [review for review in reviews if review.product_id == product.product_id]
        ratings = [item.rating for item in items]
        output.append({"product_id": product.product_id, "review_count": len(items), "average_rating": mean(ratings) if ratings else None, "rating_variance": stdev(ratings) ** 2 if len(ratings) > 1 else 0.0, "average_text_length": mean([len(item.review_text) for item in items]) if items else None})
    return output


def category_review_metrics(products: list[Product], reviews: list[Review]) -> list[dict[str, Any]]:
    """Aggregate review metrics from product category metadata."""
    categories = sorted({product.category for product in products})
    return [{"category": category, "product_count": sum(product.category == category for product in products), "review_count": len(items := [review for review in reviews if next((product.category for product in products if product.product_id == review.product_id), None) == category]), "average_rating": mean([item.rating for item in items]) if items else None, "average_review_length": mean([len(item.review_text) for item in items]) if items else None} for category in categories]


def rating_extremes(reviews: list[Review], low_threshold: int = 2, high_threshold: int = 4) -> dict[str, dict[str, Any]]:
    """Return stable low/high rating subsets with counts and ratios."""
    total = len(reviews)
    low = [review for review in reviews if review.rating <= low_threshold]
    high = [review for review in reviews if review.rating >= high_threshold]
    return {"low": {"reviews": low, "count": len(low), "ratio": len(low) / total if total else 0}, "high": {"reviews": high, "count": len(high), "ratio": len(high) / total if total else 0}}


def token_frequencies(reviews: list[Review], min_length: int = 2, stopwords: set[str] | None = None) -> dict[str, int]:
    """Count normalized Korean text tokens without a heavyweight NLP dependency."""
    excluded = {"그리고", "하지만", "정말", "너무", "그냥"} | (stopwords or set())
    tokens = []
    for review in reviews:
        tokens.extend(token for token in re.findall(r"[가-힣A-Za-z0-9]+", review.review_text.lower()) if len(token) >= min_length and token not in excluded)
    return dict(sorted(Counter(tokens).items(), key=lambda item: (-item[1], item[0])))
