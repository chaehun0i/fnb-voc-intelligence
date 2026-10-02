from pathlib import Path

from src.data.loaders import load_products, load_reviews
from src.data.quality import product_quality, review_quality


def test_quality_reports_are_structured() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    products = load_products(fixtures / "sample_products.csv")
    reviews = load_reviews(fixtures / "sample_reviews.csv", products)
    assert product_quality(products)["row_count"] == 20
    assert review_quality(reviews, products)["row_count"] == 100
