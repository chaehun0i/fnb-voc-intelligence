"""Bounded concurrent execution that preserves input ordering."""

from collections.abc import Callable, Iterable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait


def bounded_map[Input, Output](
    items: Iterable[Input],
    worker: Callable[[Input], Output],
    workers: int,
) -> list[Output]:
    """Run at most ``workers`` jobs at once and return input-ordered results."""
    if workers < 1:
        raise ValueError("workers must be positive")

    iterator = iter(enumerate(items))
    pending: dict[Future[Output], int] = {}
    results: dict[int, Output] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for _ in range(workers):
            try:
                index, item = next(iterator)
            except StopIteration:
                break
            pending[executor.submit(worker, item)] = index

        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                results[pending.pop(future)] = future.result()
                try:
                    index, item = next(iterator)
                except StopIteration:
                    continue
                pending[executor.submit(worker, item)] = index

    return [results[index] for index in range(len(results))]
