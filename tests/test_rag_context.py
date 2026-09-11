from src.rag.context import build_rag_context
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
