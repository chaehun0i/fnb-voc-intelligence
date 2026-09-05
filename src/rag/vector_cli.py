"""Command line workflows for indexing and unified review retrieval."""

import argparse
import json
from collections.abc import Callable, Sequence

from src.config import settings
from src.data.database import Connection, connect, initialize_schema
from src.data.models import Review

from .embeddings import EmbeddingProvider, FakeEmbeddingProvider
from .indexing import index_reviews
from .search_models import SearchFilters, SearchQuery
from .search_service import SearchService

LOAD_REVIEWS_SQL = """
SELECT review_id, product_id, rating, review_text, review_date, source
FROM reviews
ORDER BY review_id
"""


def build_provider() -> EmbeddingProvider:
    if settings.embedding_provider != "fake":
        raise ValueError(
            f"unsupported embedding provider: {settings.embedding_provider}"
        )
    return FakeEmbeddingProvider(
        dimension=settings.embedding_dimension,
        model=settings.embedding_model,
    )


def load_reviews(connection: Connection) -> list[Review]:
    cursor = connection.cursor()
    cursor.execute(LOAD_REVIEWS_SQL)
    return [
        Review(
            review_id=row[0],
            product_id=row[1],
            rating=row[2],
            review_text=row[3],
            review_date=row[4],
            source=row[5],
        )
        for row in cursor.fetchall()
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index and search reviews.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index", help="Index validated reviews.")
    index_parser.add_argument("--batch-size", type=int)

    search_parser = subparsers.add_parser("search", help="Run review retrieval.")
    search_parser.add_argument("query")
    search_parser.add_argument(
        "--mode", choices=("lexical", "vector", "hybrid"), default="hybrid"
    )
    search_parser.add_argument("--top-k", type=int, default=5)
    search_parser.add_argument("--candidate-k", type=int, default=20)
    search_parser.add_argument("--product")
    search_parser.add_argument("--category")
    search_parser.add_argument("--rating", type=int)
    search_parser.add_argument("--pain-point")
    search_parser.add_argument(
        "--details", action="store_true", help="Include ranking provenance."
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection_factory: Callable[[str], Connection] | None = None,
    provider_factory: Callable[[], EmbeddingProvider] | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if settings.postgresql_url is None:
        parser.error("POSTGRESQL_URL is required")

    connection = (connection_factory or connect)(settings.postgresql_url)
    needs_provider = args.command == "index" or args.mode != "lexical"
    provider = (provider_factory or build_provider)() if needs_provider else None
    try:
        initialize_schema(connection)
        cursor = connection.cursor()
        if args.command == "index":
            assert provider is not None
            batch_size = args.batch_size or settings.embedding_batch_size
            report = index_reviews(
                cursor, load_reviews(connection), provider, batch_size=batch_size
            )
            connection.commit()
            print(json.dumps(report.__dict__, ensure_ascii=False, sort_keys=True))
            return int(report.failed > 0)

        filters = SearchFilters(
            product_id=args.product,
            category=args.category,
            rating=args.rating,
            pain_point=args.pain_point,
        )
        request = SearchQuery(
            text=args.query,
            mode=args.mode,
            top_k=args.top_k,
            candidate_k=args.candidate_k,
            filters=filters,
        )
        results = SearchService(cursor, provider).search(request)
        summary_fields = {"review_id", "text", "rank", "mode"}
        for result in results:
            payload = result.model_dump(exclude_none=True)
            if not args.details:
                payload = {
                    key: value for key, value in payload.items() if key in summary_fields
                }
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        connection.close()


if __name__ == "__main__":
    main()
