"""Repeatable batch indexing for validated review models."""

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

from src.data.database import Cursor
from src.data.embedding_repository import (
    get_review_embedding,
    upsert_review_embedding,
)
from src.data.models import Review

from .embeddings import EmbeddingProvider


@dataclass(frozen=True)
class IndexingReport:
    indexed: int = 0
    skipped: int = 0
    failed: int = 0


def review_content_hash(review_text: str) -> str:
    return sha256(review_text.encode("utf-8")).hexdigest()


def index_reviews(
    cursor: Cursor,
    reviews: Sequence[Review],
    provider: EmbeddingProvider,
    batch_size: int,
) -> IndexingReport:
    """Embed changed reviews in batches and upsert their vectors."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    indexed = skipped = failed = 0
    for start in range(0, len(reviews), batch_size):
        pending: list[tuple[Review, str]] = []
        for review in reviews[start : start + batch_size]:
            digest = review_content_hash(review.review_text)
            try:
                stored = get_review_embedding(cursor, review.review_id, provider.model)
            except Exception:  # noqa: BLE001 - isolate failures per review
                failed += 1
                continue
            if (
                stored is not None
                and stored.content_hash == digest
                and stored.dimension == provider.dimension
            ):
                skipped += 1
            else:
                pending.append((review, digest))

        if not pending:
            continue
        try:
            vectors = provider.embed_batch(
                [review.review_text for review, _ in pending]
            )
        except Exception:  # noqa: BLE001 - provider errors count per batch
            failed += len(pending)
            continue
        if len(vectors) != len(pending):
            failed += len(pending)
            continue

        for (review, digest), vector in zip(pending, vectors, strict=True):
            if len(vector) != provider.dimension:
                failed += 1
                continue
            try:
                changed = upsert_review_embedding(
                    cursor,
                    review.review_id,
                    vector,
                    provider.model,
                    digest,
                )
            except Exception:  # noqa: BLE001 - isolate persistence failures
                failed += 1
            else:
                indexed += int(changed)
                skipped += int(not changed)

    return IndexingReport(indexed=indexed, skipped=skipped, failed=failed)
