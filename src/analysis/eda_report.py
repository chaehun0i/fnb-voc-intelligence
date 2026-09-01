"""CLI for generating a concise EDA JSON report."""

import argparse
import json
from pathlib import Path

from src.analysis.eda import (
    category_review_metrics,
    dataset_summary,
    rating_distribution,
    text_length_distribution,
    vocabulary_by_rating_group,
)
from src.data.loaders import load_products, load_reviews


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an EDA report.")
    parser.add_argument("--products", required=True)
    parser.add_argument("--reviews", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    products = load_products(args.products)
    reviews = load_reviews(args.reviews, products)
    report = {"products": dataset_summary(products), "reviews": dataset_summary(reviews), "ratings": rating_distribution(reviews), "text_lengths": text_length_distribution(reviews), "categories": category_review_metrics(products, reviews), "vocabulary": vocabulary_by_rating_group(reviews)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(f"EDA report written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
