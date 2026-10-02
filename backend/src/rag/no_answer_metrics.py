"""Evaluation of RAG evidence-refusal behavior."""

from dataclasses import dataclass
from typing import Literal

RagStatus = Literal["success", "no_results", "insufficient_evidence"]


@dataclass(frozen=True)
class NoAnswerMetrics:
    correct: bool
    false_answer: bool
    false_refusal: bool


def evaluate_no_answer(expected_no_answer: bool, status: RagStatus) -> NoAnswerMetrics:
    refused = status in {"no_results", "insufficient_evidence"}
    return NoAnswerMetrics(
        correct=expected_no_answer == refused,
        false_answer=expected_no_answer and not refused,
        false_refusal=not expected_no_answer and refused,
    )
