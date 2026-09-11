"""End-to-end grounded retrieval-augmented generation pipeline."""

from typing import Protocol

from .context import build_rag_context, limit_rag_context
from .generators import TextGenerator
from .prompts import PROMPT_VERSION, build_voc_prompt
from .rag_models import RagAnswer, RagRetrievalMetadata, RagSource
from .search_models import SearchQuery, SearchResult


class RetrievalService(Protocol):
    def search(self, request: SearchQuery) -> list[SearchResult]: ...


class RagPipeline:
    def __init__(
        self,
        search_service: RetrievalService,
        generator: TextGenerator,
        *,
        context_max_items: int,
        context_max_chars: int,
    ) -> None:
        self.search_service = search_service
        self.generator = generator
        self.context_max_items = context_max_items
        self.context_max_chars = context_max_chars

    def run(self, request: SearchQuery) -> RagAnswer:
        results = self.search_service.search(request)
        if not results:
            raise ValueError("RAG requires at least one retrieval result")
        context = limit_rag_context(
            build_rag_context(results),
            max_items=self.context_max_items,
            max_chars=self.context_max_chars,
        )
        if not context.items:
            raise ValueError("RAG requires at least one context item")
        prompt = build_voc_prompt(request.text, context)
        answer = self.generator.generate(prompt)
        sources = [
            RagSource(
                review_id=item.review_id,
                rank=item.rank,
                lexical_rank=item.lexical_rank,
                vector_rank=item.vector_rank,
                match_source=item.match_source,
                metadata=item.retrieval_metadata,
            )
            for item in context.items
        ]
        return RagAnswer(
            answer=answer,
            status="success",
            sources=sources,
            retrieval=RagRetrievalMetadata(
                mode=request.mode,
                top_k=request.top_k,
                retrieved_count=len(results),
                context_count=len(context.items),
            ),
            generator_model=self.generator.model,
            prompt_version=PROMPT_VERSION,
        )
