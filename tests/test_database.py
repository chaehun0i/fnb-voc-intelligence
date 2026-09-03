from src.data.database import check_health


class FakeCursor:
    def execute(self, query: str) -> None:
        self.query = query

    def fetchone(self) -> tuple[int]:
        return (1,)


class FakeConnection:
    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def close(self) -> None:
        pass


def test_health_check_uses_select_one() -> None:
    assert check_health(FakeConnection())
