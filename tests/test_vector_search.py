from math import sqrt
from typing import Any

import pytest

from src.rag.vector_search import VECTOR_SEARCH_SQL, search_similar_reviews


class RankingCursor:
    def __init__(self) -> None:
        self.embeddings = {
            "R2": ([0.8, 0.2], "두 번째 리뷰"),
            "R1": ([1.0, 0.0], "첫 번째 리뷰"),
            "R3": ([0.0, 1.0], "세 번째 리뷰"),
        }
        self.query = ""
        self.params: tuple[Any, ...] = ()
        self.results: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.query = query
        self.params = params or ()
        vector = [float(value) for value in self.params[0].strip("[]").split(",")]
        ranked = []
        for review_id, (embedding, text) in self.embeddings.items():
            dot = sum(left * right for left, right in zip(vector, embedding, strict=True))
            norms = sqrt(sum(value**2 for value in vector)) * sqrt(
                sum(value**2 for value in embedding)
            )
            distance = 1 - dot / norms
            ranked.append((review_id, 1 - distance, distance, text))
        self.results = sorted(ranked, key=lambda row: (row[2], row[0]))[
            : self.params[3]
        ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.results


def test_cosine_search_returns_ranked_review_text_and_scores() -> None:
    cursor = RankingCursor()
    results = search_similar_reviews(cursor, [1.0, 0.0], "fake-v1", top_k=2)
    assert [result.review_id for result in results] == ["R1", "R2"]
    assert results[0].score == pytest.approx(1.0)
    assert results[0].distance == pytest.approx(0.0)
    assert results[0].review_text == "첫 번째 리뷰"


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
