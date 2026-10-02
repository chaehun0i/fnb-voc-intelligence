"""Command line entry point for grounded RAG queries."""

import argparse
import json
from collections.abc import Callable, Sequence

from src.config import settings
from src.data.database import Connection, connect, initialize_schema

from .embeddings import EmbeddingProvider, FakeEmbeddingProvider
from .generators import FakeTextGenerator, TextGenerator
from .pipeline import RagPipeline
from .search_models import SearchFilters, SearchQuery
from .search_service import SearchService


def build_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider != "fake":
        raise ValueError(f"unsupported embedding provider: {settings.embedding_provider}")
    return FakeEmbeddingProvider(settings.embedding_dimension, settings.embedding_model)


def build_generator() -> TextGenerator:
    if settings.generator_provider != "fake":
        raise ValueError(f"unsupported generator provider: {settings.generator_provider}")
    return FakeTextGenerator(model=settings.generator_model)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a grounded F&B VOC RAG query.")
    parser.add_argument("query")
    parser.add_argument(
        "--mode", choices=("lexical", "vector", "hybrid"), default=None
    )
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--candidate-k", type=int, default=20)
    parser.add_argument("--product")
    parser.add_argument("--category")
    parser.add_argument("--rating", type=int)
    parser.add_argument("--pain-point")
    parser.add_argument("--details", action="store_true")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection_factory: Callable[[str], Connection] | None = None,
    embedding_factory: Callable[[], EmbeddingProvider] | None = None,
    generator_factory: Callable[[], TextGenerator] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if settings.postgresql_url is None:
        raise ValueError("POSTGRESQL_URL is required")
    mode = args.mode or settings.rag_retrieval_mode
    top_k = args.top_k or settings.rag_top_k
    provider = (
        (embedding_factory or build_embedding_provider)()
        if mode != "lexical"
        else None
    )
    generator = (generator_factory or build_generator)()
    connection = (connection_factory or connect)(settings.postgresql_url)
    try:
        initialize_schema(connection)
        request = SearchQuery(
            text=args.query,
            mode=mode,
            top_k=top_k,
            candidate_k=max(args.candidate_k, top_k),
            filters=SearchFilters(
                product_id=args.product,
                category=args.category,
                rating=args.rating,
                pain_point=args.pain_point,
            ),
        )
        pipeline = RagPipeline(
            SearchService(connection.cursor(), provider),
            generator,
            context_max_items=settings.rag_context_max_items,
            context_max_chars=settings.rag_context_max_chars,
            minimum_evidence=settings.rag_minimum_evidence,
        )
        response = pipeline.run(request)
        payload = {
            "answer": response.answer,
            "status": response.status,
            "sources": [source.review_id for source in response.sources],
        }
        if args.details:
            payload["sources"] = [
                source.model_dump(exclude_none=True) for source in response.sources
            ]
            payload["retrieval"] = response.retrieval.model_dump()
            payload["generator_model"] = response.generator_model
            payload["prompt_version"] = response.prompt_version
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    main()
