from typing import Any

import pytest

from src.rag.lexical_search import LEXICAL_SEARCH_SQL, search_reviews_lexically
from src.rag.search_models import SearchFilters


class LexicalCursor:
    def __init__(self) -> None:
        self.reviews = {
            "R2": "달콤한 음료지만 가격이 비싸요",
            "R1": "달콤한 음료가 맛있어요",
            "R3": "담백한 과자가 맛있어요",
        }
        self.metadata = {
            "R1": ("P1", "beverage", 4, "taste"),
            "R2": ("P1", "beverage", 2, "price"),
            "R3": ("P2", "snack", 4, "taste"),
        }
        self.query = ""
        self.params: tuple[Any, ...] = ()
        self.results: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.query = query
        self.params = params or ()
        terms = str(self.params[0]).split()
        filter_values = iter(self.params[1:-1])
        product_id = next(filter_values) if "r.product_id = %s" in query else None
        category = next(filter_values) if "p.category = %s" in query else None
        rating = next(filter_values) if "r.rating = %s" in query else None
        pain_point = (
            next(filter_values) if "rc.category_id = %s" in query else None
        )
        ranked = []
        for review_id, text in self.reviews.items():
            metadata = self.metadata[review_id]
            if product_id is not None and metadata[0] != product_id:
                continue
            if category is not None and metadata[1] != category:
                continue
            if rating is not None and metadata[2] != rating:
                continue
            if pain_point is not None and metadata[3] != pain_point:
                continue
            if all(term in text for term in terms):
                score = sum(text.count(term) for term in terms)
                ranked.append((review_id, score, text))
        self.results = sorted(ranked, key=lambda row: (-row[1], row[0]))[
            : self.params[-1]
        ]

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.results


def test_keyword_search_returns_deterministic_ranked_reviews() -> None:
    cursor = LexicalCursor()
    results = search_reviews_lexically(cursor, "달콤한 음료", top_k=5)
    assert [result.review_id for result in results] == ["R1", "R2"]
    assert results[0].lexical_score == 2.0
    assert results[0].text == "달콤한 음료가 맛있어요"
    assert results[0].rank == 1
    assert "ORDER BY score DESC, r.review_id ASC" in LEXICAL_SEARCH_SQL


def test_lexical_query_and_limit_are_bound_parameters() -> None:
    cursor = LexicalCursor()
    unsafe_query = "음료' OR TRUE --"
    search_reviews_lexically(cursor, unsafe_query, top_k=3)
    assert unsafe_query not in cursor.query
    assert cursor.params == (unsafe_query, 3)


@pytest.mark.parametrize(("query", "top_k"), [("", 5), ("   ", 5), ("맛", 0)])
def test_lexical_search_rejects_invalid_inputs(query: str, top_k: int) -> None:
    with pytest.raises(ValueError):
        search_reviews_lexically(LexicalCursor(), query, top_k)


def test_lexical_filters_match_vector_filter_semantics() -> None:
    cursor = LexicalCursor()
    filters = SearchFilters(
        product_id="P1", category="beverage", rating=2, pain_point="price"
    )
    results = search_reviews_lexically(cursor, "음료", top_k=5, filters=filters)
    assert [result.review_id for result in results] == ["R2"]
    assert cursor.params[1:-1] == ("P1", "beverage", 2, "price")
    assert "r.product_id = %s" in cursor.query
    assert "p.category = %s" in cursor.query
    assert "r.rating = %s" in cursor.query
    assert "rc.category_id = %s" in cursor.query


def test_lexical_filter_values_are_not_interpolated() -> None:
    cursor = LexicalCursor()
    unsafe_category = "drink' OR TRUE --"
    search_reviews_lexically(
        cursor,
        "음료",
        filters=SearchFilters(category=unsafe_category),
    )
    assert unsafe_category not in cursor.query
    assert unsafe_category in cursor.params
