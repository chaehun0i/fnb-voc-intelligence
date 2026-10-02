"""Deterministic, injectable batch execution primitives."""

from collections.abc import Callable, Iterable, Iterator


def iter_batches[T](items: Iterable[T], batch_size: int, limit: int | None = None) -> Iterator[list[T]]:
    if batch_size < 1 or limit is not None and limit < 1:
        raise ValueError("batch_size and limit must be positive")
    batch: list[T] = []
    for count, item in enumerate(items):
        if limit is not None and count >= limit:
            break
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def execute_batches[T](items: Iterable[T], batch_size: int, process: Callable[[list[T]], None], limit: int | None = None) -> int:
    completed = 0
    for batch in iter_batches(items, batch_size, limit):
        process(batch)
        completed += 1
    return completed
