from typing import Any

import pytest

from src.rag.lexical_search import LEXICAL_SEARCH_SQL, search_reviews_lexically


class LexicalCursor:
    def __init__(self) -> None:
        self.reviews = {
            "R2": "달콤한 음료지만 가격이 비싸요",
            "R1": "달콤한 음료가 맛있어요",
            "R3": "담백한 과자가 맛있어요",
        }
        self.query = ""
        self.params: tuple[Any, ...] = ()
        self.results: list[tuple[Any, ...]] = []

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.query = query
        self.params = params or ()
        terms = str(self.params[0]).split()
        ranked = []
        for review_id, text in self.reviews.items():
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
    assert results[0].score == 2.0
    assert results[0].review_text == "달콤한 음료가 맛있어요"
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
