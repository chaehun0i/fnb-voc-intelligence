"""CLI to classify a Review CSV with the versioned taxonomy."""

import argparse
import json
from pathlib import Path

from src.analysis.pain_points import classify_reviews, load_taxonomy
from src.data.loaders import load_products, load_reviews


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify review pain points.")
    parser.add_argument("--products", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--taxonomy", default=str(Path(__file__).with_name("taxonomy_v1.json")))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    products = load_products(args.products)
    reviews = load_reviews(args.reviews, products)
    result = classify_reviews(reviews, load_taxonomy(args.taxonomy))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(f"Classification written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
