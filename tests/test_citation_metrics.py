from src.rag.citation_metrics import evaluate_citations


def test_citation_precision_recall_missing_and_unsupported() -> None:
    metrics = evaluate_citations(["R1", "R2"], ["R2", "R3"])
    assert metrics.precision == metrics.recall == 0.5
    assert metrics.missing == ["R1"]
    assert metrics.unsupported == ["R3"]


def test_empty_citations_are_safe() -> None:
    metrics = evaluate_citations(["R1"], [])
    assert metrics.precision == metrics.recall == 0.0
    assert metrics.missing == ["R1"]
