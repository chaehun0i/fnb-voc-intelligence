"""Cosine similarity search over persisted review embeddings."""

from src.data.database import Cursor

from .search_models import SearchFilters, SearchResult

VECTOR_SEARCH_BASE_SQL = """
WITH query_vector AS (SELECT %s::vector AS embedding)
SELECT r.review_id,
       1 - (e.embedding <=> query_vector.embedding) AS score,
       e.embedding <=> query_vector.embedding AS distance,
       r.review_text
FROM review_embeddings AS e
JOIN reviews AS r ON r.review_id = e.review_id
JOIN products AS p ON p.product_id = r.product_id
CROSS JOIN query_vector
"""

VECTOR_SEARCH_ORDER_SQL = """
ORDER BY distance ASC, r.review_id ASC
LIMIT %s
"""

VECTOR_SEARCH_SQL = (
    VECTOR_SEARCH_BASE_SQL
    + "WHERE e.model = %s AND e.dimension = %s\n"
    + VECTOR_SEARCH_ORDER_SQL
)


VectorSearchFilters = SearchFilters


def _vector_literal(embedding: list[float]) -> str:
    if not embedding:
        raise ValueError("query embedding must not be empty")
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def search_similar_reviews(
    cursor: Cursor,
    query_embedding: list[float],
    model: str,
    top_k: int = 5,
    filters: SearchFilters | None = None,
) -> list[SearchResult]:
    """Return deterministic nearest reviews using pgvector cosine distance."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    clauses = ["e.model = %s", "e.dimension = %s"]
    params: list[object] = [
        _vector_literal(query_embedding),
        model,
        len(query_embedding),
    ]
    filters = filters or SearchFilters()
    if filters.product_id is not None:
        clauses.append("r.product_id = %s")
        params.append(filters.product_id)
    if filters.category is not None:
        clauses.append("p.category = %s")
        params.append(filters.category)
    if filters.rating is not None:
        clauses.append("r.rating = %s")
        params.append(filters.rating)
    if filters.pain_point is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM review_classifications AS rc "
            "WHERE rc.review_id = r.review_id AND rc.category_id = %s)"
        )
        params.append(filters.pain_point)
    query = (
        VECTOR_SEARCH_BASE_SQL
        + "WHERE "
        + " AND ".join(clauses)
        + "\n"
        + VECTOR_SEARCH_ORDER_SQL
    )
    params.append(top_k)
    cursor.execute(query, tuple(params))
    return [
        SearchResult(
            review_id=row[0],
            text=row[3],
            rank=rank,
            mode="vector",
            vector_score=float(row[1]),
            metadata={"distance": float(row[2])},
        )
        for rank, row in enumerate(cursor.fetchall(), start=1)
    ]
