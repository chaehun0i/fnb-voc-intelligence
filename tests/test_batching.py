import pytest

from src.rag.batching import execute_batches, iter_batches


def test_batches_are_stable_incremental_and_limited() -> None:
    assert list(iter_batches(["R3", "R1", "R2"], 2, limit=2)) == [["R3", "R1"]]
    seen: list[list[int]] = []
    assert execute_batches(range(5), 2, seen.append) == 3
    assert seen == [[0, 1], [2, 3], [4]]


def test_batches_validate_boundaries() -> None:
    with pytest.raises(ValueError):
        list(iter_batches([], 0))
