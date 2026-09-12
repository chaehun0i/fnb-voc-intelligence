import json
from pathlib import Path

import pytest

from src.rag.evaluation_loader import load_evaluation_cases


def test_jsonl_dataset_loads_deterministically() -> None:
    path = Path("tests/fixtures/sample_rag_evaluation.jsonl")
    cases = load_evaluation_cases(path)
    assert [case.case_id for case in cases] == ["price-1", "no-answer-1"]
    assert cases[0].relevant_review_ids == ["R1"]


def test_json_dataset_loads(tmp_path: Path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"case_id": "c", "version": "v1", "query": "q"}]), encoding="utf-8")
    assert load_evaluation_cases(path)[0].case_id == "c"


@pytest.mark.parametrize(
    "content",
    ["{", '{"case_id":"c"}', '[{"case_id":"c","version":"v1","query":"q"},{"case_id":"c","version":"v1","query":"q"}]'],
)
def test_invalid_dataset_fails_clearly(tmp_path: Path, content: str) -> None:
    path = tmp_path / "cases.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((TypeError, ValueError)):
        load_evaluation_cases(path)
