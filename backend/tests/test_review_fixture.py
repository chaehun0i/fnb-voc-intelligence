import csv
from pathlib import Path

from src.data import Review

FIXTURES = Path(__file__).parent / "fixtures"


def test_all_sample_reviews_validate() -> None:
    with (FIXTURES / "sample_reviews.csv").open(encoding="utf-8", newline="") as file:
        reviews = [Review(**row) for row in csv.DictReader(file)]
    assert len(reviews) == 100


def test_review_ids_and_product_references_are_valid() -> None:
    with (FIXTURES / "sample_reviews.csv").open(encoding="utf-8", newline="") as file:
        reviews = list(csv.DictReader(file))
    with (FIXTURES / "sample_products.csv").open(encoding="utf-8", newline="") as file:
        products = {row["product_id"] for row in csv.DictReader(file)}
    assert len({row["review_id"] for row in reviews}) == len(reviews)
    assert {row["product_id"] for row in reviews} <= products
