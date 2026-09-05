import pytest
from pydantic import ValidationError

from src.rag.search_models import SearchFilters, SearchQuery, SearchResult


def test_search_query_normalizes_text_and_validates_sizes() -> None:
    query = SearchQuery(text="  달콤한 음료  ", top_k=3, candidate_k=10)
    assert query.text == "달콤한 음료"
    assert query.mode == "hybrid"
    assert query.filters == SearchFilters()


@pytest.mark.parametrize(
    "values",
    [
        {"text": "query", "mode": "unknown"},
        {"text": "query", "top_k": 0},
        {"text": "query", "top_k": 10, "candidate_k": 5},
        {"text": "query", "filters": {"rating": 6}},
    ],
)
def test_search_query_rejects_invalid_contract(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SearchQuery(**values)


def test_shared_result_keeps_explicit_score_and_metadata() -> None:
    result = SearchResult(
        review_id="R1",
        text="맛있는 음료",
        rank=1,
        mode="vector",
        vector_score=0.8,
        metadata={"category": "beverage", "rating": 4},
    )
    assert result.vector_score == 0.8
    assert result.metadata["category"] == "beverage"


def test_result_requires_a_score_and_positive_rank() -> None:
    with pytest.raises(ValidationError):
        SearchResult(review_id="R1", text="리뷰", rank=0, mode="hybrid")


def test_hybrid_result_requires_ranking_provenance() -> None:
    with pytest.raises(ValidationError, match="match source"):
        SearchResult(
            review_id="R1",
            text="리뷰",
            rank=1,
            mode="hybrid",
            fused_score=0.1,
        )

    result = SearchResult(
        review_id="R1",
        text="리뷰",
        rank=1,
        mode="hybrid",
        lexical_score=0.5,
        vector_score=0.2,
        fused_score=0.03,
        lexical_rank=2,
        vector_rank=1,
        match_source="both",
    )
    assert result.fused_score == 0.03
    assert result.lexical_rank == 2
    assert result.vector_rank == 1
    assert not hasattr(result, "score")
