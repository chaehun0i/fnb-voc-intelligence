from src.data.database import (
    PGVECTOR_EXTENSION_SQL,
    check_health,
    initialize_schema,
)


class FakeCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(query)

    def fetchone(self) -> tuple[int]:
        return (1,)


class FakeConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def close(self) -> None:
        pass


def test_health_check_uses_select_one() -> None:
    assert check_health(FakeConnection())


def test_schema_initialization_is_repeatable() -> None:
    connection = FakeConnection()
    initialize_schema(connection)
    initialize_schema(connection)
    assert connection.fake_cursor.queries.count(PGVECTOR_EXTENSION_SQL) == 2
    assert "IF NOT EXISTS" in PGVECTOR_EXTENSION_SQL
