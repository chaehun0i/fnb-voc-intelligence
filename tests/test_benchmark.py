from src.rag.benchmark import run_benchmark, synthetic_review_ids


def test_synthetic_benchmark_input_and_batch_count_are_deterministic() -> None:
    assert synthetic_review_ids(3) == [
        "benchmark-000000",
        "benchmark-000001",
        "benchmark-000002",
    ]
    result = run_benchmark(5, 2)
    assert result["count"] == 5 and result["batches"] == 3
