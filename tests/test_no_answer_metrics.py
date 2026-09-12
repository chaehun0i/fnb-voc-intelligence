import pytest

from src.rag.no_answer_metrics import evaluate_no_answer


@pytest.mark.parametrize(
    ("expected", "status", "correct", "false_answer", "false_refusal"),
    [
        (True, "no_results", True, False, False),
        (True, "success", False, True, False),
        (False, "insufficient_evidence", False, False, True),
        (False, "success", True, False, False),
    ],
)
def test_no_answer_behavior(expected: bool, status: str, correct: bool, false_answer: bool, false_refusal: bool) -> None:
    metrics = evaluate_no_answer(expected, status)  # type: ignore[arg-type]
    assert (metrics.correct, metrics.false_answer, metrics.false_refusal) == (correct, false_answer, false_refusal)
