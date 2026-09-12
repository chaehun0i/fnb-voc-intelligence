import json
from pathlib import Path

from src.rag.evaluation_cli import main
from src.rag.rag_models import RagAnswer, RagRetrievalMetadata, RagSource
from src.rag.search_models import SearchQuery


class Pipeline:
    def run(self, request: SearchQuery) -> RagAnswer:
        return RagAnswer(answer="a", status="success", sources=[RagSource(review_id="R1", rank=1)], retrieval=RagRetrievalMetadata(mode="hybrid", top_k=request.top_k, retrieved_count=1, context_count=1), prompt_version="v1")


def test_evaluation_cli_outputs_json_and_summary(capsys) -> None:
    code = main(["--dataset", str(Path("tests/fixtures/sample_rag_evaluation.jsonl")), "--k", "1"], pipeline_factory=Pipeline)
    lines = capsys.readouterr().out.splitlines()
    assert code in (0, 1)
    assert json.loads(lines[0])["cases"] == 2
    assert lines[1].startswith("RAG evaluation")
