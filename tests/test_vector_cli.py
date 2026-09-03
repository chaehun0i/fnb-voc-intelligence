import json
from datetime import date
from types import SimpleNamespace
from typing import Any

from src.rag import vector_cli
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.indexing import IndexingReport
from src.rag.vector_search import VectorSearchResult


class CliCursor:
    def __init__(self) -> None:
        self.query = ""

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.query = query

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self.query == vector_cli.LOAD_REVIEWS_SQL:
            return [
                ("R1", "P1", 4, "달고 맛있어요", date(2026, 9, 4), "test")
            ]
        return []


class CliConnection:
    def __init__(self) -> None:
        self.fake_cursor = CliCursor()
        self.committed = False
        self.closed = False

    def cursor(self) -> CliCursor:
        return self.fake_cursor

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def configure_cli(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        vector_cli,
        "settings",
        SimpleNamespace(
            postgresql_url="postgresql://test",
            embedding_provider="fake",
            embedding_model="fake-v1",
            embedding_dimension=3,
            embedding_batch_size=10,
        ),
    )


def test_index_command_uses_fake_embedding_and_reports_counts(
    monkeypatch: Any, capsys: Any
) -> None:
    configure_cli(monkeypatch)
    connection = CliConnection()
    captured: dict[str, Any] = {}

    def fake_index(
        cursor: object,
        reviews: list[object],
        provider: FakeEmbeddingProvider,
        batch_size: int,
    ) -> IndexingReport:
        captured.update(
            reviews=reviews, provider=provider, batch_size=batch_size, cursor=cursor
        )
        return IndexingReport(indexed=1)

    monkeypatch.setattr(vector_cli, "index_reviews", fake_index)
    code = vector_cli.main(
        ["index", "--batch-size", "2"],
        connection_factory=lambda _url: connection,
    )
    assert code == 0
    assert isinstance(captured["provider"], FakeEmbeddingProvider)
    assert captured["batch_size"] == 2
    assert connection.committed and connection.closed
    assert json.loads(capsys.readouterr().out) == {
        "failed": 0,
        "indexed": 1,
        "skipped": 0,
    }


def test_search_command_passes_filters_and_prints_results(
    monkeypatch: Any, capsys: Any
) -> None:
    configure_cli(monkeypatch)
    connection = CliConnection()
    captured: dict[str, Any] = {}

    def fake_search(*args: Any, **kwargs: Any) -> list[VectorSearchResult]:
        captured.update(args=args, kwargs=kwargs)
        return [VectorSearchResult("R1", 0.9, 0.1, "달고 맛있어요")]

    monkeypatch.setattr(vector_cli, "search_similar_reviews", fake_search)
    code = vector_cli.main(
        [
            "search",
            "달콤한 음료",
            "--top-k",
            "3",
            "--category",
            "beverage",
            "--pain-point",
            "taste",
        ],
        connection_factory=lambda _url: connection,
        provider_factory=lambda: FakeEmbeddingProvider(dimension=3),
    )
    assert code == 0
    assert len(captured["args"][1]) == 3
    assert captured["kwargs"]["top_k"] == 3
    assert captured["kwargs"]["filters"].category == "beverage"
    assert captured["kwargs"]["filters"].pain_point == "taste"
    assert json.loads(capsys.readouterr().out)["review_id"] == "R1"
    assert connection.closed
