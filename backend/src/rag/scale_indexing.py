"""Incremental vector indexing built on the reusable batch executor."""

from collections.abc import Iterable

from src.data.database import Cursor
from src.data.models import Review

from .batching import iter_batches
from .embeddings import EmbeddingProvider
from .indexing import IndexingReport, index_reviews


def index_review_stream(
    cursor: Cursor,
    reviews: Iterable[Review],
    provider: EmbeddingProvider,
    batch_size: int,
    limit: int | None = None,
) -> IndexingReport:
    """Index a review stream incrementally, retaining hash-based skipping."""
    total = IndexingReport()
    for batch in iter_batches(reviews, batch_size=batch_size, limit=limit):
        report = index_reviews(cursor, batch, provider, batch_size=len(batch))
        total = IndexingReport(
            indexed=total.indexed + report.indexed,
            skipped=total.skipped + report.skipped,
            failed=total.failed + report.failed,
        )
    return total
