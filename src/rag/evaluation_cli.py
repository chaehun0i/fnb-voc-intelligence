"""CLI report for deterministic RAG evaluation datasets."""

import argparse
import json
from collections.abc import Callable, Sequence
from pathlib import Path

from src.config import settings

from .evaluation_loader import load_evaluation_cases
from .evaluation_runner import AnswerPipeline, EvaluationReport, run_evaluation


def evaluate_report(report: EvaluationReport) -> dict[str, object]:
    thresholds = {"recall": settings.evaluation_recall_threshold, "precision": settings.evaluation_precision_threshold, "citation_recall": settings.evaluation_citation_threshold}
    passed = all(report.averages[key] >= value for key, value in thresholds.items())
    return {"cases": len(report.cases), "averages": report.averages, "thresholds": thresholds, "passed": passed}


def main(argv: Sequence[str] | None = None, *, pipeline_factory: Callable[[], AnswerPipeline] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RAG evaluation.")
    parser.add_argument("--dataset", type=Path, default=settings.evaluation_dataset_path)
    parser.add_argument("--k", type=int, default=settings.evaluation_retrieval_k)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args(argv)
    if pipeline_factory is None:
        raise RuntimeError("CLI pipeline factory must be configured by the application")
    summary = evaluate_report(run_evaluation(pipeline_factory(), load_evaluation_cases(args.dataset), args.k))
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if not args.json_only:
        state = "PASS" if summary["passed"] else "FAIL"
        print(f"RAG evaluation {state}: {summary['cases']} cases")
    return 0 if summary["passed"] else 1
