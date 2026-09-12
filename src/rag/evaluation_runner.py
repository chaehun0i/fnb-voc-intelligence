"""Batch evaluator over RAG cases with deterministic aggregate metrics."""

from dataclasses import dataclass
from typing import Protocol

from .citation_metrics import CitationMetrics, evaluate_citations
from .evaluation_cases import EvaluationCase
from .evaluation_metrics import mrr, ndcg_at_k, precision_at_k, recall_at_k
from .no_answer_metrics import NoAnswerMetrics, evaluate_no_answer
from .rag_models import RagAnswer
from .search_models import SearchQuery


class AnswerPipeline(Protocol):
    def run(self, request: SearchQuery) -> RagAnswer: ...


@dataclass(frozen=True)
class CaseEvaluation:
    case_id: str
    recall: float
    precision: float
    mrr: float
    ndcg: float
    citations: CitationMetrics
    no_answer: NoAnswerMetrics


@dataclass(frozen=True)
class EvaluationReport:
    cases: list[CaseEvaluation]
    averages: dict[str, float]


def run_evaluation(pipeline: AnswerPipeline, cases: list[EvaluationCase], k: int) -> EvaluationReport:
    evaluated = []
    for case in cases:
        answer = pipeline.run(SearchQuery(text=case.query, top_k=k))
        ids = [source.review_id for source in answer.sources]
        evaluated.append(CaseEvaluation(case.case_id, recall_at_k(case.relevant_review_ids, ids, k), precision_at_k(case.relevant_review_ids, ids, k), mrr(case.relevant_review_ids, ids, k), ndcg_at_k(case.relevant_review_ids, ids, k), evaluate_citations(case.relevant_review_ids, ids), evaluate_no_answer(case.expected_no_answer, answer.status)))
    keys = ("recall", "precision", "mrr", "ndcg", "citation_precision", "citation_recall", "no_answer_accuracy")
    count = len(evaluated)
    averages = {key: (sum(_value(item, key) for item in evaluated) / count if count else 0.0) for key in keys}
    return EvaluationReport(evaluated, averages)


def _value(item: CaseEvaluation, key: str) -> float:
    if key == "citation_precision": return item.citations.precision
    if key == "citation_recall": return item.citations.recall
    if key == "no_answer_accuracy": return float(item.no_answer.correct)
    return getattr(item, key)
