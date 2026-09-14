import threading
from time import sleep

import pytest

from src.rag.concurrency import bounded_map


def test_bounded_map_preserves_input_result_order() -> None:
    assert bounded_map([3, 2, 1], lambda value: value * 2, workers=2) == [6, 4, 2]


def test_bounded_map_limits_active_workers() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def work(value: int) -> int:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        sleep(0.01)
        with lock:
            active -= 1
        return value

    assert bounded_map(range(6), work, workers=2) == list(range(6))
    assert peak == 2


def test_bounded_map_rejects_invalid_worker_count() -> None:
    with pytest.raises(ValueError, match="workers"):
        bounded_map([], lambda value: value, workers=0)
