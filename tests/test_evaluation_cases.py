import pytest
from pydantic import ValidationError

from src.rag.evaluation_cases import EvaluationCase


def test_evaluation_case_is_versioned_and_normalized() -> None:
    case = EvaluationCase(
        case_id=" case-1 ",
        version="v1",
        query=" 가격 불만 ",
        expected_pain_points=["price"],
        relevant_review_ids=["R1"],
        answer_requirements=["cite R1"],
    )
    assert case.case_id == "case-1"
    assert case.query == "가격 불만"


@pytest.mark.parametrize(
    "values",
    [
        {"case_id": "", "version": "v1", "query": "q"},
        {"case_id": "c", "version": "v1", "query": "q", "relevant_review_ids": ["R1", "R1"]},
    ],
)
def test_evaluation_case_rejects_invalid_schema(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EvaluationCase(**values)
