"""Command-line validation for product and review CSV files."""

import argparse

from .loaders import DataValidationError, load_products, load_reviews
from .quality import product_quality, review_quality


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate product and review CSV files.")
    parser.add_argument("--products", required=True)
    parser.add_argument("--reviews", required=True)
    args = parser.parse_args()
    try:
        products = load_products(args.products)
        reviews = load_reviews(args.reviews, products)
    except DataValidationError as error:
        print(f"Validation failed: {error}")
        return 1
    print(f"Validation passed: {product_quality(products)['row_count']} products, {review_quality(reviews, products)['row_count']} reviews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
