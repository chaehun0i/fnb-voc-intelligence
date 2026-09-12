"""Deterministic source-grounding checks."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CitationMetrics:
    precision: float
    recall: float
    missing: list[str]
    unsupported: list[str]


def evaluate_citations(expected: list[str], cited: list[str]) -> CitationMetrics:
    expected_set, cited_set = set(expected), set(cited)
    supported = expected_set & cited_set
    return CitationMetrics(
        precision=len(supported) / len(cited_set) if cited_set else 0.0,
        recall=len(supported) / len(expected_set) if expected_set else 0.0,
        missing=sorted(expected_set - cited_set),
        unsupported=sorted(cited_set - expected_set),
    )
