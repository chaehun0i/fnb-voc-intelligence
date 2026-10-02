import pytest

from src.rag.evaluation_metrics import mrr, ndcg_at_k, precision_at_k, recall_at_k


def test_recall_and_precision_at_k() -> None:
    assert recall_at_k(["R1", "R2"], ["R2", "R3"], 2) == 0.5
    assert precision_at_k(["R1", "R2"], ["R2", "R3"], 2) == 0.5
    assert recall_at_k([], ["R1"], 1) == 0.0
    assert precision_at_k(["R1"], [], 1) == 0.0


def test_mrr_and_ndcg_at_k_handle_edges() -> None:
    assert mrr(["R2"], ["R1", "R2"], 2) == 0.5
    assert ndcg_at_k(["R2"], ["R1", "R2"], 2) == pytest.approx(0.6309297535714575)
    assert ndcg_at_k([], ["R1"], 1) == 0.0
    with pytest.raises(ValueError):
        mrr([], [], 0)
