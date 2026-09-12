"""Pure retrieval and ranking metrics for deterministic evaluation."""


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

