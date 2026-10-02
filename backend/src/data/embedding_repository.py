"""Persistence operations for review embeddings."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .database import Cursor

UPSERT_REVIEW_EMBEDDING_SQL = """
INSERT INTO review_embeddings (
    review_id, model, dimension, embedding, content_hash
)
VALUES (%s, %s, %s, %s::vector, %s)
ON CONFLICT (review_id, model) DO UPDATE SET
    dimension = EXCLUDED.dimension,
    embedding = EXCLUDED.embedding,
    content_hash = EXCLUDED.content_hash,
    updated_at = CURRENT_TIMESTAMP
WHERE review_embeddings.content_hash IS DISTINCT FROM EXCLUDED.content_hash
   OR review_embeddings.dimension IS DISTINCT FROM EXCLUDED.dimension
RETURNING review_id
"""

GET_REVIEW_EMBEDDING_SQL = """
SELECT review_id, model, dimension, embedding::text, content_hash,
       created_at, updated_at
FROM review_embeddings
WHERE review_id = %s AND model = %s
"""


@dataclass(frozen=True)
class ReviewEmbedding:
    review_id: str
    model: str
    dimension: int
    embedding: list[float]
    content_hash: str
    created_at: datetime
    updated_at: datetime


def _vector_literal(embedding: list[float]) -> str:
    if not embedding:
        raise ValueError("embedding must not be empty")
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def _parse_vector(value: Any) -> list[float]:
    if isinstance(value, str):
        return [float(item) for item in value.strip("[]").split(",") if item]
    return [float(item) for item in value]


def upsert_review_embedding(
    cursor: Cursor,
    review_id: str,
    embedding: list[float],
    model: str,
    content_hash: str,
) -> bool:
    """Insert or update a vector, returning whether storage changed."""
    cursor.execute(
        UPSERT_REVIEW_EMBEDDING_SQL,
        (review_id, model, len(embedding), _vector_literal(embedding), content_hash),
    )
    return cursor.fetchone() is not None


def get_review_embedding(
    cursor: Cursor, review_id: str, model: str
) -> ReviewEmbedding | None:
    cursor.execute(GET_REVIEW_EMBEDDING_SQL, (review_id, model))
    row = cursor.fetchone()
    if row is None:
        return None
    return ReviewEmbedding(
        review_id=row[0],
        model=row[1],
        dimension=row[2],
        embedding=_parse_vector(row[3]),
        content_hash=row[4],
        created_at=row[5],
        updated_at=row[6],
    )
