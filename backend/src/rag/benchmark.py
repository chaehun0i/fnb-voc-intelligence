"""Deterministic, dependency-free synthetic batching benchmark."""

import argparse
from time import perf_counter

from .batching import iter_batches


def synthetic_review_ids(count: int) -> list[str]:
    """Produce a stable synthetic workload without source data or network access."""
    if count < 1:
        raise ValueError("count must be positive")
    return [f"benchmark-{number:06d}" for number in range(count)]


def run_benchmark(count: int, batch_size: int) -> dict[str, int | float]:
    """Measure only deterministic local batch iteration."""
    started = perf_counter()
    batches = list(iter_batches(synthetic_review_ids(count), batch_size))
    elapsed = perf_counter() - started
    return {"batches": len(batches), "count": count, "elapsed_seconds": elapsed}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark deterministic batching.")
    parser.add_argument("--count", type=int, default=1_000)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    print(run_benchmark(args.count, args.batch_size))


if __name__ == "__main__":
    main()
