from datetime import date

from src.analysis.eda import dataset_summary, rating_distribution
from src.data import Review


def test_dataset_summary_is_deterministic() -> None:
    reviews = [Review(review_id="R1", product_id="P1", rating=5, review_text="좋아요", review_date=date(2026, 1, 1), source="test")]
    summary = dataset_summary(reviews)
    assert summary["row_count"] == 1
    assert summary["columns"] == ["review_id", "product_id", "rating", "review_text", "review_date", "source"]
    assert summary["null_counts"]["rating"] == 0


def test_rating_distribution_covers_valid_ratings() -> None:
    reviews = [Review(review_id=f"R{rating}", product_id="P1", rating=rating, review_text="좋아요", review_date=date(2026, 1, 1), source="test") for rating in range(1, 6)]
    assert rating_distribution(reviews)["frequency"] == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
