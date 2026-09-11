from typing import Any

import pytest
from pydantic import ValidationError

from src.rag import search_service
from src.rag.embeddings import EmbeddingUnavailableError, FakeEmbeddingProvider
from src.rag.search_models import SearchFilters, SearchQuery, SearchResult


def result(mode: str) -> SearchResult:
    score = {f"{mode}_score": 0.5}
    return SearchResult(
        review_id="R1", text="review", rank=1, mode=mode, **score
    )


def test_service_dispatches_lexical_mode_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_lexical(*args: Any, **kwargs: Any) -> list[SearchResult]:
        captured.update(args=args, kwargs=kwargs)
        return [result("lexical")]

    monkeypatch.setattr(search_service, "search_reviews_lexically", fake_lexical)
    filters = SearchFilters(rating=2)
    results = search_service.SearchService(object()).search(
        SearchQuery(text="가격", mode="lexical", top_k=3, filters=filters)
    )
    assert results[0].mode == "lexical"
    assert captured["kwargs"] == {"top_k": 3, "filters": filters}


def test_service_dispatches_vector_and_hybrid_modes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    provider = FakeEmbeddingProvider(dimension=4)

    def fake_vector(*args: Any, **kwargs: Any) -> list[SearchResult]:
        calls["vector"] = (args, kwargs)
        return [result("vector")]

    def fake_hybrid(*args: Any, **kwargs: Any) -> list[SearchResult]:
        calls["hybrid"] = (args, kwargs)
        return []

    monkeypatch.setattr(search_service, "search_similar_reviews", fake_vector)
    monkeypatch.setattr(search_service, "search_reviews_hybrid", fake_hybrid)
    service = search_service.SearchService(object(), provider, fusion_constant=30)
    service.search(SearchQuery(text="맛", mode="vector", top_k=2))
    service.search(
        SearchQuery(text="맛", mode="hybrid", top_k=2, candidate_k=7)
    )
    assert len(calls["vector"][0][1]) == 4
    assert calls["vector"][1]["top_k"] == 2
    assert calls["hybrid"][1]["candidate_k"] == 7
    assert calls["hybrid"][1]["fusion_constant"] == 30


def test_service_validates_requests_and_provider_requirements() -> None:
    with pytest.raises(ValidationError):
        SearchQuery(text="query", mode="invalid")
    with pytest.raises(ValidationError):
        SearchQuery(text="query", filters={"rating": 0})
    with pytest.raises(EmbeddingUnavailableError):
        search_service.SearchService(object()).search(
            SearchQuery(text="query", mode="vector")
        )
    with pytest.raises(ValueError, match="fusion_constant"):
        search_service.SearchService(object(), fusion_constant=-1)


def test_service_handles_empty_query_consistently() -> None:
    service = search_service.SearchService(object())
    for mode in ("lexical", "vector", "hybrid"):
        assert service.search(SearchQuery(text="  ", mode=mode)) == []
