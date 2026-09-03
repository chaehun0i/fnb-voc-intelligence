"""Small PostgreSQL connection boundary, independent of domain logic."""

from typing import Protocol


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
