from typing import Any

import pytest

from src.rag import hybrid_search
from src.rag.embeddings import EmbeddingUnavailableError, FakeEmbeddingProvider
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
    [("query", 0, 20), ("query", 10, 5)],
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


def test_empty_query_returns_no_results_without_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected(*args: Any, **kwargs: Any) -> list[SearchResult]:
        raise AssertionError("retrieval should not run")

    monkeypatch.setattr(hybrid_search, "search_reviews_lexically", unexpected)
    assert hybrid_search.search_reviews_hybrid(object(), "   ", None) == []


def test_missing_provider_falls_back_to_lexical_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hybrid_search,
        "search_reviews_lexically",
        lambda *args, **kwargs: [result("A", 1, "lexical")],
    )
    results = hybrid_search.search_reviews_hybrid(object(), "query", None)
    assert [item.review_id for item in results] == ["A"]
    assert results[0].match_source == "lexical"


def test_explicit_embedding_unavailability_falls_back_without_hiding_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hybrid_search,
        "search_reviews_lexically",
        lambda *args, **kwargs: [result("A", 1, "lexical")],
    )

    class UnavailableProvider(FakeEmbeddingProvider):
        def embed(self, text: str) -> list[float]:
            raise EmbeddingUnavailableError("temporarily unavailable")

    results = hybrid_search.search_reviews_hybrid(
        object(), "query", UnavailableProvider()
    )
    assert results[0].match_source == "lexical"

    class BrokenProvider(FakeEmbeddingProvider):
        def embed(self, text: str) -> list[float]:
            raise RuntimeError("unexpected provider bug")

    with pytest.raises(RuntimeError, match="unexpected provider bug"):
        hybrid_search.search_reviews_hybrid(object(), "query", BrokenProvider())
