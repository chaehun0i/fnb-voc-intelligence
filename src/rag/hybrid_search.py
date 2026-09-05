"""Hybrid retrieval orchestration for lexical and vector candidates."""

from src.data.database import Cursor

from .embeddings import EmbeddingProvider, EmbeddingUnavailableError
from .lexical_search import search_reviews_lexically
from .rank_fusion import reciprocal_rank_fusion
from .search_models import SearchFilters, SearchResult
from .vector_search import search_similar_reviews


def search_reviews_hybrid(
    cursor: Cursor,
    query: str,
    provider: EmbeddingProvider | None,
    *,
    top_k: int = 5,
    candidate_k: int = 20,
    filters: SearchFilters | None = None,
    fusion_constant: int = 60,
) -> list[SearchResult]:
    """Retrieve both candidate sets and return their fused top-k ranking."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if candidate_k < top_k:
        raise ValueError("candidate_k must be greater than or equal to top_k")
    if not query.strip():
        return []
    filters = filters or SearchFilters()
    lexical_results = search_reviews_lexically(
        cursor, query, top_k=candidate_k, filters=filters
    )
    vector_results: list[SearchResult] = []
    if provider is not None:
        try:
            query_embedding = provider.embed(query)
        except EmbeddingUnavailableError:
            pass
        else:
            vector_results = search_similar_reviews(
                cursor,
                query_embedding,
                provider.model,
                top_k=candidate_k,
                filters=filters,
            )
    return reciprocal_rank_fusion(
        lexical_results,
        vector_results,
        fusion_constant=fusion_constant,
        top_k=top_k,
    )
