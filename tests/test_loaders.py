from pathlib import Path

import pytest

from src.data.loaders import DataValidationError, load_products, load_reviews

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_fixtures() -> None:
    products = load_products(FIXTURES / "sample_products.csv")
    assert len(load_reviews(FIXTURES / "sample_reviews.csv", products)) == 100


@pytest.mark.parametrize("name", ["missing.csv", "empty.csv"])
def test_missing_or_empty_file_fails(tmp_path: Path, name: str) -> None:
    path = tmp_path / name
    if name == "empty.csv":
        path.touch()
    with pytest.raises(DataValidationError):
        load_products(path)


def test_missing_column_and_invalid_rating_fail(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"
    missing.write_text("product_id\nP1\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="missing columns"):
        load_products(missing)
    bad = tmp_path / "bad.csv"
    bad.write_text("review_id,product_id,rating,review_text,review_date,source\nR1,P001,9,좋아요,2026-08-01,x\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="row 2"):
        load_reviews(bad, load_products(FIXTURES / "sample_products.csv"))


def test_orphan_product_fails(tmp_path: Path) -> None:
    orphan = tmp_path / "orphan.csv"
    orphan.write_text("review_id,product_id,rating,review_text,review_date,source\nR1,P999,5,좋아요,2026-08-01,x\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="orphan"):
        load_reviews(orphan, load_products(FIXTURES / "sample_products.csv"))
