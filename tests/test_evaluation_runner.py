from src.rag.evaluation_cases import EvaluationCase
from src.rag.evaluation_runner import run_evaluation
from src.rag.rag_models import RagAnswer, RagRetrievalMetadata, RagSource
from src.rag.search_models import SearchQuery


class FakePipeline:
    def run(self, request: SearchQuery) -> RagAnswer:
        source = [] if "없음" in request.text else [RagSource(review_id="R1", rank=1)]
        return RagAnswer(answer="답변", status="no_results" if not source else "success", sources=source, retrieval=RagRetrievalMetadata(mode="hybrid", top_k=request.top_k, retrieved_count=len(source), context_count=len(source)), prompt_version="v1")


def test_runner_returns_per_case_and_aggregate_metrics() -> None:
    cases = [EvaluationCase(case_id="c1", version="v1", query="가격", relevant_review_ids=["R1"]), EvaluationCase(case_id="c2", version="v1", query="없음", expected_no_answer=True)]
    report = run_evaluation(FakePipeline(), cases, k=5)
    assert [item.case_id for item in report.cases] == ["c1", "c2"]
    assert report.cases[0].recall == 1.0
    assert report.cases[1].no_answer.correct
    assert report.averages["recall"] == 0.5
