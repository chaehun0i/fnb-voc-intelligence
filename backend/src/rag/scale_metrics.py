"""Operational counters and progress snapshots for scale jobs."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ScaleProgress:
    processed: int
    succeeded: int
    skipped: int
    failed: int
    elapsed_seconds: float
    throughput_per_second: float


class ScaleMetrics:
    """Collect job counters and publish immutable progress snapshots."""

    def __init__(self, clock: Callable[[], float], on_progress: Callable[[ScaleProgress], None] | None = None) -> None:
        self._clock = clock
        self._started_at = clock()
        self._on_progress = on_progress
        self.processed = 0
        self.succeeded = 0
        self.skipped = 0
        self.failed = 0

    def record(self, *, succeeded: int = 0, skipped: int = 0, failed: int = 0) -> ScaleProgress:
        """Add one completed unit and emit an up-to-date progress snapshot."""
        self.succeeded += succeeded
        self.skipped += skipped
        self.failed += failed
        self.processed += succeeded + skipped + failed
        progress = self.snapshot()
        if self._on_progress is not None:
            self._on_progress(progress)
        return progress

    def snapshot(self) -> ScaleProgress:
        elapsed = max(0.0, self._clock() - self._started_at)
        throughput = self.processed / elapsed if elapsed else 0.0
        return ScaleProgress(
            processed=self.processed,
            succeeded=self.succeeded,
            skipped=self.skipped,
            failed=self.failed,
            elapsed_seconds=elapsed,
            throughput_per_second=throughput,
        )
