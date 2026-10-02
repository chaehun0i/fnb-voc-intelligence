"""Command line validation for external ingestion files."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .file_adapters import read_file


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an external ingestion source.")
    parser.add_argument("--source-type", choices=("csv", "json", "jsonl"), required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--source", default="external")
    parser.add_argument("--mapping", default="{}")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    mapping = json.loads(args.mapping)
    records = read_file(Path(args.path), args.source_type, args.source)
    if args.limit is not None:
        records = records[: args.limit]
    print(json.dumps({"source": args.source, "input_count": len(records), "mapping_fields": len(mapping), "dry_run": args.dry_run}, ensure_ascii=False, sort_keys=True))
    return 0
