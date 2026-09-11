"""One validated service boundary for lexical, vector, and hybrid retrieval."""

from src.data.database import Cursor

from .embeddings import EmbeddingProvider, EmbeddingUnavailableError
from .hybrid_search import search_reviews_hybrid
from .lexical_search import search_reviews_lexically
from .search_models import SearchQuery, SearchResult
from .vector_search import search_similar_reviews


class SearchService:
    def __init__(
        self,
        cursor: Cursor,
        provider: EmbeddingProvider | None = None,
        *,
        fusion_constant: int = 60,
    ) -> None:
        if fusion_constant < 0:
            raise ValueError("fusion_constant must not be negative")
        self.cursor = cursor
        self.provider = provider
        self.fusion_constant = fusion_constant

    def search(self, request: SearchQuery) -> list[SearchResult]:
        """Dispatch a validated request to its selected retrieval mode."""
        if not request.text:
            return []
        if request.mode == "lexical":
            return search_reviews_lexically(
                self.cursor,
                request.text,
                top_k=request.top_k,
                filters=request.filters,
            )
        if request.mode == "vector":
            if self.provider is None:
                raise EmbeddingUnavailableError(
                    "vector mode requires an embedding provider"
                )
            return search_similar_reviews(
                self.cursor,
                self.provider.embed(request.text),
                self.provider.model,
                top_k=request.top_k,
                filters=request.filters,
            )
        return search_reviews_hybrid(
            self.cursor,
            request.text,
            self.provider,
            top_k=request.top_k,
            candidate_k=request.candidate_k,
            filters=request.filters,
            fusion_constant=self.fusion_constant,
        )
