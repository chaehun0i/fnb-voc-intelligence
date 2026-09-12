"""Pure retrieval and ranking metrics for deterministic evaluation."""

from math import log2


def recall_at_k(relevant: list[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    expected = set(relevant)
    return len(expected & set(retrieved[:k])) / len(expected) if expected else 0.0


def precision_at_k(relevant: list[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    window = retrieved[:k]
    return len(set(window) & set(relevant)) / len(window) if window else 0.0


def mrr(relevant: list[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    for rank, review_id in enumerate(retrieved[:k], start=1):
        if review_id in set(relevant):
            return 1 / rank
    return 0.0


def ndcg_at_k(relevant: list[str], retrieved: list[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive")
    expected = set(relevant)
    dcg = sum(1 / log2(rank + 1) for rank, item in enumerate(retrieved[:k], 1) if item in expected)
    ideal = sum(1 / log2(rank + 1) for rank in range(1, min(len(expected), k) + 1))
    return dcg / ideal if ideal else 0.0
