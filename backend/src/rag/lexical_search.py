"""PostgreSQL full-text retrieval for review text."""

from src.data.database import Cursor

from .search_models import SearchFilters, SearchResult

LEXICAL_SEARCH_BASE_SQL = """
WITH query AS (SELECT plainto_tsquery('simple', %s) AS terms)
SELECT r.review_id,
       ts_rank_cd(to_tsvector('simple', r.review_text), query.terms) AS score,
       r.review_text
FROM reviews AS r
JOIN products AS p ON p.product_id = r.product_id
CROSS JOIN query
"""

LEXICAL_SEARCH_ORDER_SQL = """
ORDER BY score DESC, r.review_id ASC
LIMIT %s
"""

LEXICAL_SEARCH_SQL = (
    LEXICAL_SEARCH_BASE_SQL
    + "WHERE to_tsvector('simple', r.review_text) @@ query.terms\n"
    + LEXICAL_SEARCH_ORDER_SQL
)


def search_reviews_lexically(
    cursor: Cursor,
    query: str,
    top_k: int = 5,
    filters: SearchFilters | None = None,
) -> list[SearchResult]:
    """Return keyword-matching reviews with deterministic PostgreSQL ranking."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    clauses = ["to_tsvector('simple', r.review_text) @@ query.terms"]
    params: list[object] = [query]
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
    sql = (
        LEXICAL_SEARCH_BASE_SQL
        + "WHERE "
        + " AND ".join(clauses)
        + "\n"
        + LEXICAL_SEARCH_ORDER_SQL
    )
    params.append(top_k)
    cursor.execute(sql, tuple(params))
    return [
        SearchResult(
            review_id=row[0],
            text=row[2],
            rank=rank,
            mode="lexical",
            lexical_score=float(row[1]),
        )
        for rank, row in enumerate(cursor.fetchall(), start=1)
    ]
