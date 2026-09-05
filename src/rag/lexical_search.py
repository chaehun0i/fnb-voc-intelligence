"""PostgreSQL full-text retrieval for review text."""

from dataclasses import dataclass

from src.data.database import Cursor

LEXICAL_SEARCH_SQL = """
WITH query AS (SELECT plainto_tsquery('simple', %s) AS terms)
SELECT r.review_id,
       ts_rank_cd(to_tsvector('simple', r.review_text), query.terms) AS score,
       r.review_text
FROM reviews AS r
CROSS JOIN query
WHERE to_tsvector('simple', r.review_text) @@ query.terms
ORDER BY score DESC, r.review_id ASC
LIMIT %s
"""


@dataclass(frozen=True)
class LexicalSearchResult:
    review_id: str
    score: float
    review_text: str


def search_reviews_lexically(
    cursor: Cursor, query: str, top_k: int = 5
) -> list[LexicalSearchResult]:
    """Return keyword-matching reviews with deterministic PostgreSQL ranking."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    cursor.execute(LEXICAL_SEARCH_SQL, (query, top_k))
    return [
        LexicalSearchResult(
            review_id=row[0], score=float(row[1]), review_text=row[2]
        )
        for row in cursor.fetchall()
    ]
