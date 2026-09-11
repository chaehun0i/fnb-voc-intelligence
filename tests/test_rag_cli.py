import json
from types import SimpleNamespace
from typing import Any

from src.rag import rag_cli
from src.rag.generators import FakeTextGenerator
from src.rag.rag_models import RagAnswer, RagRetrievalMetadata, RagSource


class FakeCursor:
    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor()

    def close(self) -> None:
        self.closed = True


def test_rag_cli_returns_answer_sources_and_details(
    monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setattr(
        rag_cli,
        "settings",
        SimpleNamespace(
            postgresql_url="postgresql://test",
            rag_retrieval_mode="hybrid",
            rag_top_k=5,
            rag_context_max_items=4,
            rag_context_max_chars=500,
            rag_minimum_evidence=1,
        ),
    )
    captured: dict[str, Any] = {}

    class FakePipeline:
        def __init__(self, service: object, generator: object, **kwargs: Any) -> None:
            captured.update(generator=generator, kwargs=kwargs)

        def run(self, request: object) -> RagAnswer:
            captured["request"] = request
            return RagAnswer(
                answer="가격 불만이 있습니다. [R1]",
                status="success",
                sources=[RagSource(review_id="R1", rank=1, match_source="both")],
                retrieval=RagRetrievalMetadata(
                    mode="hybrid", top_k=3, retrieved_count=2, context_count=1
                ),
                generator_model="fake-v1",
                prompt_version="fnb-voc-rag-v1",
            )

    monkeypatch.setattr(rag_cli, "RagPipeline", FakePipeline)
    connection = FakeConnection()
    code = rag_cli.main(
        [
            "가격 불만은?",
            "--mode",
            "hybrid",
            "--top-k",
            "3",
            "--category",
            "beverage",
            "--details",
        ],
        connection_factory=lambda _url: connection,
        embedding_factory=lambda: None,
        generator_factory=lambda: FakeTextGenerator(),
    )
    assert code == 0 and connection.closed
    assert captured["request"].top_k == 3
    assert captured["request"].filters.category == "beverage"
    output = json.loads(capsys.readouterr().out)
    assert output["answer"].startswith("가격 불만")
    assert output["sources"][0]["review_id"] == "R1"
    assert output["retrieval"]["mode"] == "hybrid"


def test_lexical_rag_cli_skips_embedding_provider(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(
        rag_cli,
        "settings",
        SimpleNamespace(
            postgresql_url="postgresql://test",
            rag_retrieval_mode="lexical",
            rag_top_k=5,
            rag_context_max_items=5,
            rag_context_max_chars=500,
            rag_minimum_evidence=1,
        ),
    )

    class FakePipeline:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run(self, request: object) -> RagAnswer:
            return RagAnswer(
                answer="근거가 충분하지 않습니다.",
                status="no_results",
                retrieval=RagRetrievalMetadata(
                    mode="lexical", top_k=5, retrieved_count=0, context_count=0
                ),
                prompt_version="fnb-voc-rag-v1",
            )

    monkeypatch.setattr(rag_cli, "RagPipeline", FakePipeline)
    rag_cli.main(
        ["질문", "--mode", "lexical"],
        connection_factory=lambda _url: FakeConnection(),
        embedding_factory=lambda: (_ for _ in ()).throw(AssertionError()),
        generator_factory=lambda: FakeTextGenerator(),
    )
    assert json.loads(capsys.readouterr().out)["status"] == "no_results"
