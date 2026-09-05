import json
from datetime import date
from types import SimpleNamespace
from typing import Any

from src.rag import vector_cli
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.indexing import IndexingReport
from src.rag.search_models import SearchResult


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

    class FakeSearchService:
        def __init__(self, cursor: object, provider: object) -> None:
            captured.update(cursor=cursor, provider=provider)

        def search(self, request: object) -> list[SearchResult]:
            captured["request"] = request
            return [
                SearchResult(
                    review_id="R1",
                    text="달고 맛있어요",
                    rank=1,
                    mode="hybrid",
                    lexical_score=0.5,
                    vector_score=0.9,
                    fused_score=0.03,
                    lexical_rank=2,
                    vector_rank=1,
                    match_source="both",
                )
            ]

    monkeypatch.setattr(vector_cli, "SearchService", FakeSearchService)
    code = vector_cli.main(
        [
            "search",
            "달콤한 음료",
            "--mode",
            "hybrid",
            "--top-k",
            "3",
            "--candidate-k",
            "9",
            "--category",
            "beverage",
            "--pain-point",
            "taste",
            "--details",
        ],
        connection_factory=lambda _url: connection,
        provider_factory=lambda: FakeEmbeddingProvider(dimension=3),
    )
    assert code == 0
    assert isinstance(captured["provider"], FakeEmbeddingProvider)
    request = captured["request"]
    assert request.mode == "hybrid"
    assert request.top_k == 3 and request.candidate_k == 9
    assert request.filters.category == "beverage"
    assert request.filters.pain_point == "taste"
    output = json.loads(capsys.readouterr().out)
    assert output["review_id"] == "R1"
    assert output["fused_score"] == 0.03
    assert output["match_source"] == "both"
    assert connection.closed


def test_lexical_cli_does_not_require_embeddings(
    monkeypatch: Any, capsys: Any
) -> None:
    configure_cli(monkeypatch)
    connection = CliConnection()
    captured: dict[str, Any] = {}

    class FakeSearchService:
        def __init__(self, cursor: object, provider: object) -> None:
            captured["provider"] = provider

        def search(self, request: object) -> list[SearchResult]:
            captured["request"] = request
            return [
                SearchResult(
                    review_id="R1",
                    text="가격이 비싸요",
                    rank=1,
                    mode="lexical",
                    lexical_score=0.5,
                )
            ]

    monkeypatch.setattr(vector_cli, "SearchService", FakeSearchService)
    code = vector_cli.main(
        ["search", "가격", "--mode", "lexical"],
        connection_factory=lambda _url: connection,
        provider_factory=lambda: (_ for _ in ()).throw(AssertionError()),
    )
    assert code == 0
    assert captured["provider"] is None
    assert captured["request"].mode == "lexical"
    assert json.loads(capsys.readouterr().out) == {
        "mode": "lexical",
        "rank": 1,
        "review_id": "R1",
        "text": "가격이 비싸요",
    }


def test_vector_cli_uses_fake_embedding_provider(
    monkeypatch: Any, capsys: Any
) -> None:
    configure_cli(monkeypatch)
    connection = CliConnection()
    captured: dict[str, Any] = {}

    class FakeSearchService:
        def __init__(self, cursor: object, provider: object) -> None:
            captured["provider"] = provider

        def search(self, request: object) -> list[SearchResult]:
            captured["request"] = request
            return []

    monkeypatch.setattr(vector_cli, "SearchService", FakeSearchService)
    code = vector_cli.main(
        ["search", "맛", "--mode", "vector"],
        connection_factory=lambda _url: connection,
    )
    assert code == 0
    assert isinstance(captured["provider"], FakeEmbeddingProvider)
    assert captured["request"].mode == "vector"
    assert capsys.readouterr().out == ""
