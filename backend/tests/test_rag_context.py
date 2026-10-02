import pytest

from src.rag.context import build_rag_context, limit_rag_context
from src.rag.search_models import SearchResult


def hybrid_result(review_id: str, rank: int) -> SearchResult:
    return SearchResult(
        review_id=review_id,
        text=f"review {review_id}",
        rank=rank,
        mode="hybrid",
        fused_score=0.1,
        lexical_rank=rank,
        match_source="lexical",
        metadata={
            "product_id": "P1",
            "category": "beverage",
            "pain_points": ["taste", "price"],
            "distance": 0.2,
        },
    )


def test_search_results_become_ordered_structured_context() -> None:
    context = build_rag_context([hybrid_result("R2", 2), hybrid_result("R1", 1)])
    assert [item.review_id for item in context.items] == ["R1", "R2"]
    item = context.items[0]
    assert item.text == "review R1"
    assert item.product_id == "P1"
    assert item.category == "beverage"
    assert item.pain_points == ["taste", "price"]
    assert item.lexical_rank == 1
    assert item.match_source == "lexical"
    assert item.retrieval_metadata["distance"] == 0.2


def test_context_budget_preserves_order_and_exact_boundaries() -> None:
    context = build_rag_context(
        [hybrid_result("R1", 1), hybrid_result("R2", 2), hybrid_result("R3", 3)]
    )
    limited = limit_rag_context(context, max_items=2, max_chars=18)
    assert [item.review_id for item in limited.items] == ["R1", "R2"]
    assert limited.character_count == 18


def test_context_budget_excludes_overflow_without_truncation() -> None:
    context = build_rag_context(
        [hybrid_result("LONG", 1), hybrid_result("R2", 2)]
    )
    limited = limit_rag_context(context, max_items=5, max_chars=9)
    assert [item.review_id for item in limited.items] == ["R2"]
    assert limited.items[0].text == "review R2"


@pytest.mark.parametrize(("items", "chars"), [(0, 10), (1, 0)])
def test_context_budget_rejects_invalid_limits(items: int, chars: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        limit_rag_context(build_rag_context([]), max_items=items, max_chars=chars)
