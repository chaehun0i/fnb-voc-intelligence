"""CLI for controlled, large-scale review vector indexing."""

import argparse
import json
from collections.abc import Callable, Sequence

from src.config import settings
from src.data.database import Connection, connect, initialize_schema

from .scale_indexing import index_review_stream
from .scale_metrics import ScaleMetrics, ScaleProgress
from .scale_models import ScaleJobConfig
from .vector_cli import build_provider, load_reviews


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run resumable large-scale vector indexing.")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


def run_indexing(config: ScaleJobConfig, on_progress: Callable[[ScaleProgress], None]) -> ScaleProgress:
    """Run the database-backed stream indexer and publish its final progress."""
    if settings.postgresql_url is None:
        raise ValueError("POSTGRESQL_URL is required")
    connection: Connection = connect(settings.postgresql_url)
    try:
        initialize_schema(connection)
        report = index_review_stream(
            connection.cursor(),
            load_reviews(connection),
            build_provider(),
            batch_size=config.batch_size,
            limit=config.limit,
        )
        connection.commit()
        metrics = ScaleMetrics(clock=lambda: 0.0, on_progress=on_progress)
        return metrics.record(
            succeeded=report.indexed,
            skipped=report.skipped,
            failed=report.failed,
        )
    finally:
        connection.close()


def main(
    argv: Sequence[str] | None = None,
    *,
    runner: Callable[[ScaleJobConfig, Callable[[ScaleProgress], None]], ScaleProgress]
    | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    config = ScaleJobConfig(
        batch_size=args.batch_size,
        workers=args.workers,
        retries=args.retries,
        resume=args.resume,
        limit=args.limit,
    )
    progress_events: list[ScaleProgress] = []
    progress = (runner or run_indexing)(config, progress_events.append)
    for event in progress_events:
        print(json.dumps(event.__dict__, ensure_ascii=False, sort_keys=True))
    print(json.dumps(progress.__dict__, ensure_ascii=False, sort_keys=True))
    return int(progress.failed > 0)


if __name__ == "__main__":
    main()
