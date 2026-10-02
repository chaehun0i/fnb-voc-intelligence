"""Small PostgreSQL connection boundary, independent of domain logic."""

from typing import Any, Protocol

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
    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None: ...
    def fetchone(self) -> tuple[Any, ...] | None: ...
    def fetchall(self) -> list[tuple[Any, ...]]: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def commit(self) -> None: ...
    def close(self) -> None: ...


def connect(postgresql_url: str) -> Connection:
    """Open a PostgreSQL connection without leaking driver details to services."""
    from psycopg import connect as psycopg_connect

    return psycopg_connect(postgresql_url)


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
