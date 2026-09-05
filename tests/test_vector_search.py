from math import sqrt
from typing import Any

import pytest

from src.rag.vector_search import (
    VECTOR_SEARCH_SQL,
    VectorSearchFilters,
    search_similar_reviews,
)


class RankingCursor:
    def __init__(self) -> None:
        self.embeddings = {
            "R2": ([0.8, 0.2], "두 번째 리뷰"),
            "R1": ([1.0, 0.0], "첫 번째 리뷰"),
            "R3": ([0.0, 1.0], "세 번째 리뷰"),
        }
        self.metadata = {
            "R1": ("P1", "snack", 2, "price"),
            "R2": ("P1", "beverage", 4, "taste"),
            "R3": ("P2", "beverage", 2, "price"),
        }
        self.query = ""
        self.params: tuple[Any, ...] = ()
        self.results: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.query = query
        self.params = params or ()
        vector = [float(value) for value in self.params[0].strip("[]").split(",")]
        ranked = []
        filter_values = iter(self.params[3:-1])
        product_id = next(filter_values) if "r.product_id = %s" in query else None
        category = next(filter_values) if "p.category = %s" in query else None
        rating = next(filter_values) if "r.rating = %s" in query else None
        pain_point = (
            next(filter_values) if "rc.category_id = %s" in query else None
        )
        for review_id, (embedding, text) in self.embeddings.items():
            metadata = self.metadata[review_id]
            if product_id is not None and metadata[0] != product_id:
                continue
            if category is not None and metadata[1] != category:
                continue
            if rating is not None and metadata[2] != rating:
                continue
            if pain_point is not None and metadata[3] != pain_point:
                continue
            dot = sum(left * right for left, right in zip(vector, embedding, strict=True))
            norms = sqrt(sum(value**2 for value in vector)) * sqrt(
                sum(value**2 for value in embedding)
            )
            distance = 1 - dot / norms
            ranked.append((review_id, 1 - distance, distance, text))
        self.results = sorted(ranked, key=lambda row: (row[2], row[0]))[
            : self.params[-1]
        ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.results


def test_cosine_search_returns_ranked_review_text_and_scores() -> None:
    cursor = RankingCursor()
    results = search_similar_reviews(cursor, [1.0, 0.0], "fake-v1", top_k=2)
    assert [result.review_id for result in results] == ["R1", "R2"]
    assert results[0].vector_score == pytest.approx(1.0)
    assert results[0].metadata["distance"] == pytest.approx(0.0)
    assert results[0].text == "첫 번째 리뷰"
    assert results[0].rank == 1


def test_search_query_is_parameterized_and_deterministic() -> None:
    cursor = RankingCursor()
    unsafe_model = "model' OR TRUE --"
    search_similar_reviews(cursor, [1.0, 0.0], unsafe_model, top_k=1)
    assert unsafe_model not in cursor.query
    assert unsafe_model in cursor.params
    assert "<=>" in VECTOR_SEARCH_SQL
    assert "ORDER BY distance ASC, r.review_id ASC" in VECTOR_SEARCH_SQL


@pytest.mark.parametrize("top_k", [0, -1])
def test_search_rejects_non_positive_top_k(top_k: int) -> None:
    with pytest.raises(ValueError, match="top_k"):
        search_similar_reviews(RankingCursor(), [1.0], "fake-v1", top_k)


def test_search_filters_are_composable_and_parameterized() -> None:
    cursor = RankingCursor()
    filters = VectorSearchFilters(
        product_id="P1", category="snack", rating=2, pain_point="price"
    )
    results = search_similar_reviews(
        cursor, [1.0, 0.0], "fake-v1", top_k=5, filters=filters
    )
    assert [result.review_id for result in results] == ["R1"]
    assert cursor.params[3:-1] == ("P1", "snack", 2, "price")
    assert "r.product_id = %s" in cursor.query
    assert "p.category = %s" in cursor.query
    assert "r.rating = %s" in cursor.query
    assert "rc.category_id = %s" in cursor.query


def test_search_rejects_invalid_rating_filter() -> None:
    with pytest.raises(ValueError, match="rating"):
        VectorSearchFilters(rating=6)
