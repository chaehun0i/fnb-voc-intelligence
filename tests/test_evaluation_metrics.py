from src.rag.evaluation_metrics import precision_at_k, recall_at_k


def test_recall_and_precision_at_k() -> None:
    assert recall_at_k(["R1", "R2"], ["R2", "R3"], 2) == 0.5
    assert precision_at_k(["R1", "R2"], ["R2", "R3"], 2) == 0.5
    assert recall_at_k([], ["R1"], 1) == 0.0
    assert precision_at_k(["R1"], [], 1) == 0.0
