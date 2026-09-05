from typing import Any

import pytest

from src.rag import hybrid_search
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.search_models import SearchFilters, SearchResult


def result(review_id: str, rank: int, mode: str) -> SearchResult:
    values: dict[str, Any] = {
        "review_id": review_id,
        "text": f"review {review_id}",
        "rank": rank,
        "mode": mode,
    }
    values[f"{mode}_score"] = 1 / rank
    return SearchResult(**values)


def test_hybrid_search_fuses_lexical_and_vector_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def fake_lexical(*args: Any, **kwargs: Any) -> list[SearchResult]:
        calls["lexical"] = (args, kwargs)
        return [result("A", 1, "lexical"), result("B", 2, "lexical")]

    def fake_vector(*args: Any, **kwargs: Any) -> list[SearchResult]:
        calls["vector"] = (args, kwargs)
        return [result("B", 1, "vector"), result("C", 2, "vector")]

    monkeypatch.setattr(hybrid_search, "search_reviews_lexically", fake_lexical)
    monkeypatch.setattr(hybrid_search, "search_similar_reviews", fake_vector)
    filters = SearchFilters(category="beverage")
    results = hybrid_search.search_reviews_hybrid(
        object(),
        "달콤한 음료",
        FakeEmbeddingProvider(dimension=3),
        top_k=2,
        candidate_k=8,
        filters=filters,
        fusion_constant=10,
    )
    assert [item.review_id for item in results] == ["B", "A"]
    assert calls["lexical"][1] == {"top_k": 8, "filters": filters}
    assert calls["vector"][1] == {"top_k": 8, "filters": filters}
    assert len(calls["vector"][0][1]) == 3


@pytest.mark.parametrize(
    ("query", "top_k", "candidate_k"),
    [("", 5, 20), ("query", 0, 20), ("query", 10, 5)],
)
def test_hybrid_search_rejects_invalid_sizes(
    query: str, top_k: int, candidate_k: int
) -> None:
    with pytest.raises(ValueError):
        hybrid_search.search_reviews_hybrid(
            object(),
            query,
            FakeEmbeddingProvider(),
            top_k=top_k,
            candidate_k=candidate_k,
        )
