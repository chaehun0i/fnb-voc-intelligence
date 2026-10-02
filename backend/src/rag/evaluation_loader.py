"""JSON and JSONL loader for versioned evaluation cases."""

import json
from pathlib import Path

from .evaluation_cases import EvaluationCase


def load_evaluation_cases(path: Path) -> list[EvaluationCase]:
    if not path.is_file():
        raise ValueError(f"evaluation dataset not found: {path}")
    try:
        if path.suffix.lower() == ".jsonl":
            records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        elif path.suffix.lower() == ".json":
            records = json.loads(path.read_text(encoding="utf-8"))
        else:
            raise ValueError("dataset must use .json or .jsonl")
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid evaluation JSON: {error.msg}") from error
    if not isinstance(records, list):
        raise TypeError("evaluation dataset must be a list of records")
    try:
        cases = [EvaluationCase.model_validate(record) for record in records]
    except Exception as error:
        raise ValueError(f"invalid evaluation record: {error}") from error
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evaluation case_id")
    return cases
