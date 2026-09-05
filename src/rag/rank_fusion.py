"""Deterministic Reciprocal Rank Fusion for retrieval result lists."""

from collections.abc import Sequence

from .search_models import SearchResult


def _best_by_review(results: Sequence[SearchResult]) -> dict[str, SearchResult]:
    best: dict[str, SearchResult] = {}
    for result in sorted(results, key=lambda item: (item.rank, item.review_id, item.text)):
        best.setdefault(result.review_id, result)
    return best


def reciprocal_rank_fusion(
    lexical_results: Sequence[SearchResult],
    vector_results: Sequence[SearchResult],
    *,
    fusion_constant: int = 60,
    top_k: int | None = None,
) -> list[SearchResult]:
    """Fuse ranks while counting each review at most once per retrieval source."""
    if fusion_constant < 0:
        raise ValueError("fusion_constant must not be negative")
    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be positive")

    lexical = _best_by_review(lexical_results)
    vector = _best_by_review(vector_results)
    scores: dict[str, float] = {}
    for review_id, result in lexical.items():
        scores[review_id] = 1 / (fusion_constant + result.rank)
    for review_id, result in vector.items():
        scores[review_id] = scores.get(review_id, 0.0) + 1 / (
            fusion_constant + result.rank
        )

    review_ids = sorted(
        scores,
        key=lambda review_id: (
            -scores[review_id],
            min(
                result.rank
                for result in (lexical.get(review_id), vector.get(review_id))
                if result is not None
            ),
            review_id,
        ),
    )
    if top_k is not None:
        review_ids = review_ids[:top_k]

    fused = []
    for rank, review_id in enumerate(review_ids, start=1):
        lexical_result = lexical.get(review_id)
        vector_result = vector.get(review_id)
        preferred = lexical_result or vector_result
        assert preferred is not None
        metadata = dict(vector_result.metadata) if vector_result else {}
        if lexical_result:
            metadata.update(lexical_result.metadata)
        fused.append(
            SearchResult(
                review_id=review_id,
                text=preferred.text,
                rank=rank,
                mode="hybrid",
                lexical_score=(
                    lexical_result.lexical_score if lexical_result else None
                ),
                vector_score=vector_result.vector_score if vector_result else None,
                fused_score=scores[review_id],
                metadata=metadata,
            )
        )
    return fused
