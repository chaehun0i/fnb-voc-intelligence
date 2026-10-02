from datetime import date

import pytest

from src.data.models import Product, Review
from src.ingestion.loading import load_records


def product() -> Product:
    return Product(product_id="P1", brand="B", product_name="N", category="C", price=1, weight_g=1, calories_kcal=1, protein_g=1, carbohydrate_g=1, sugar_g=1, fat_g=1, sodium_mg=1, source="s")


def review(product_id: str = "P1") -> Review:
    return Review(review_id="R1", product_id=product_id, rating=5, review_text="좋아요", review_date=date(2026, 1, 1), source="s")


class Connection:
    def __init__(self) -> None: self.committed = False
    def cursor(self) -> object: return object()
    def commit(self) -> None: self.committed = True


def test_load_dry_run_does_not_write() -> None:
    result = load_records(Connection(), [product()], [review()], dry_run=True)
    assert result.dry_run and result.products == result.reviews == 1


def test_load_rejects_orphan_before_writing() -> None:
    with pytest.raises(ValueError, match="orphan"):
        load_records(Connection(), [product()], [review("missing")])
