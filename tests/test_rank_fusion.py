import pytest

from src.rag.rank_fusion import reciprocal_rank_fusion
from src.rag.search_models import SearchResult


def lexical(review_id: str, rank: int) -> SearchResult:
    return SearchResult(
        review_id=review_id,
        text=f"review {review_id}",
        rank=rank,
        mode="lexical",
        lexical_score=1 / rank,
    )


def vector(review_id: str, rank: int) -> SearchResult:
    return SearchResult(
        review_id=review_id,
        text=f"review {review_id}",
        rank=rank,
        mode="vector",
        vector_score=1 - rank / 10,
    )


def test_rrf_combines_rankings_reproducibly() -> None:
    results = reciprocal_rank_fusion(
        [lexical("A", 1), lexical("B", 2)],
        [vector("B", 1), vector("C", 2)],
        fusion_constant=60,
    )
    assert [result.review_id for result in results] == ["B", "A", "C"]
    assert results[0].fused_score == pytest.approx(1 / 62 + 1 / 61)
    assert [result.rank for result in results] == [1, 2, 3]


def test_rrf_ignores_duplicate_results_from_one_source() -> None:
    results = reciprocal_rank_fusion(
        [lexical("A", 3), lexical("A", 1)],
        [vector("B", 1), vector("B", 4)],
        fusion_constant=10,
    )
    assert [result.review_id for result in results] == ["A", "B"]
    assert results[0].fused_score == pytest.approx(1 / 11)


def test_rrf_handles_missing_source_and_top_k() -> None:
    results = reciprocal_rank_fusion(
        [lexical("A", 1), lexical("B", 2)], [], fusion_constant=20, top_k=1
    )
    assert [result.review_id for result in results] == ["A"]
    assert results[0].vector_score is None


@pytest.mark.parametrize(
    ("constant", "top_k"),
    [(-1, None), (60, 0)],
)
def test_rrf_rejects_invalid_parameters(constant: int, top_k: int | None) -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([], [], fusion_constant=constant, top_k=top_k)
