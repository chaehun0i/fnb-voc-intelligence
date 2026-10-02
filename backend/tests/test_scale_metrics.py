from src.rag.scale_metrics import ScaleMetrics, ScaleProgress


def test_metrics_track_counts_time_throughput_and_progress_callback() -> None:
    time = 10.0
    published: list[ScaleProgress] = []
    metrics = ScaleMetrics(lambda: time, published.append)
    time = 12.0
    progress = metrics.record(succeeded=3, skipped=1, failed=1)
    assert progress == ScaleProgress(5, 3, 1, 1, 2.0, 2.5)
    assert published == [progress]


def test_metrics_clamps_negative_elapsed_time() -> None:
    clock_values = iter([10.0, 9.0])
    metrics = ScaleMetrics(lambda: next(clock_values))
    assert metrics.record(succeeded=1).throughput_per_second == 0.0
