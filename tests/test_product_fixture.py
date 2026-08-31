import csv
from pathlib import Path

from src.data import Product

FIXTURE = Path(__file__).parent / "fixtures" / "sample_products.csv"


def test_all_sample_products_validate() -> None:
    with FIXTURE.open(encoding="utf-8", newline="") as file:
        products = [Product(**row) for row in csv.DictReader(file)]
    assert len(products) == 20


def test_sample_product_ids_are_unique() -> None:
    with FIXTURE.open(encoding="utf-8", newline="") as file:
        identifiers = [row["product_id"] for row in csv.DictReader(file)]
    assert len(identifiers) == len(set(identifiers))
