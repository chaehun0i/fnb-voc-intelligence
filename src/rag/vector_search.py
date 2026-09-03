"""Cosine similarity search over persisted review embeddings."""

from dataclasses import dataclass

from src.data.database import Cursor

VECTOR_SEARCH_SQL = """
WITH query_vector AS (SELECT %s::vector AS embedding)
SELECT r.review_id,
       1 - (e.embedding <=> query_vector.embedding) AS score,
       e.embedding <=> query_vector.embedding AS distance,
       r.review_text
FROM review_embeddings AS e
JOIN reviews AS r ON r.review_id = e.review_id
CROSS JOIN query_vector
WHERE e.model = %s AND e.dimension = %s
ORDER BY distance ASC, r.review_id ASC
LIMIT %s
"""


@dataclass(frozen=True)
class VectorSearchResult:
    review_id: str
    score: float
    distance: float
    review_text: str


def _vector_literal(embedding: list[float]) -> str:
    if not embedding:
        raise ValueError("query embedding must not be empty")
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def search_similar_reviews(
    cursor: Cursor,
    query_embedding: list[float],
    model: str,
    top_k: int = 5,
) -> list[VectorSearchResult]:
    """Return deterministic nearest reviews using pgvector cosine distance."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    cursor.execute(
        VECTOR_SEARCH_SQL,
        (_vector_literal(query_embedding), model, len(query_embedding), top_k),
    )
    return [
        VectorSearchResult(
            review_id=row[0],
            score=float(row[1]),
            distance=float(row[2]),
            review_text=row[3],
        )
        for row in cursor.fetchall()
    ]
