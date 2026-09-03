"""Small PostgreSQL connection boundary, independent of domain logic."""

from typing import Protocol

from .schema import (
    PRODUCTS_TABLE_SQL,
    REVIEW_CLASSIFICATIONS_TABLE_SQL,
    REVIEW_EMBEDDINGS_TABLE_SQL,
    REVIEWS_TABLE_SQL,
    TAXONOMY_CATEGORIES_TABLE_SQL,
    TAXONOMY_KEYWORDS_TABLE_SQL,
)

PGVECTOR_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector"


class Cursor(Protocol):
    def execute(self, query: str) -> None: ...
    def fetchone(self) -> tuple[int] | None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def close(self) -> None: ...


def check_health(connection: Connection) -> bool:
    """Execute the minimal portable PostgreSQL health query."""
    cursor = connection.cursor()
    cursor.execute("SELECT 1")
    return cursor.fetchone() == (1,)


def initialize_schema(connection: Connection) -> None:
    """Enable pgvector and create tables in foreign-key dependency order."""
    cursor = connection.cursor()
    for statement in (
        PGVECTOR_EXTENSION_SQL,
        PRODUCTS_TABLE_SQL,
        REVIEWS_TABLE_SQL,
        TAXONOMY_CATEGORIES_TABLE_SQL,
        TAXONOMY_KEYWORDS_TABLE_SQL,
        REVIEW_CLASSIFICATIONS_TABLE_SQL,
        REVIEW_EMBEDDINGS_TABLE_SQL,
    ):
        cursor.execute(statement)
