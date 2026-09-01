from datetime import date

from src.analysis.eda import (
    category_review_metrics,
    dataset_summary,
    rating_distribution,
    rating_extremes,
    text_length_distribution,
    token_frequencies,
)
from src.data import Product, Review


def test_dataset_summary_is_deterministic() -> None:
    reviews = [Review(review_id="R1", product_id="P1", rating=5, review_text="좋아요", review_date=date(2026, 1, 1), source="test")]
    summary = dataset_summary(reviews)
    assert summary["row_count"] == 1
    assert summary["columns"] == ["review_id", "product_id", "rating", "review_text", "review_date", "source"]
    assert summary["null_counts"]["rating"] == 0


def test_rating_distribution_covers_valid_ratings() -> None:
    reviews = [Review(review_id=f"R{rating}", product_id="P1", rating=rating, review_text="좋아요", review_date=date(2026, 1, 1), source="test") for rating in range(1, 6)]
    assert rating_distribution(reviews)["frequency"] == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}


def test_text_lengths_handle_empty_and_normal_input() -> None:
    assert text_length_distribution([])["min"] is None
    review = Review(review_id="R", product_id="P", rating=5, review_text="좋아요", review_date=date(2026, 1, 1), source="x")
    assert text_length_distribution([review])["max"] == 3


def test_category_metrics_include_categories_without_reviews() -> None:
    product = Product(product_id="P", brand="b", product_name="n", category="샐러드", price=1, weight_g=1, calories_kcal=1, protein_g=1, carbohydrate_g=1, sugar_g=1, fat_g=1, sodium_mg=1, source="x")
    assert category_review_metrics([product], [])[0]["review_count"] == 0


def test_rating_extremes_include_threshold_boundaries() -> None:
    reviews = [Review(review_id=f"R{rating}", product_id="P", rating=rating, review_text="좋아요", review_date=date(2026, 1, 1), source="x") for rating in range(1, 6)]
    result = rating_extremes(reviews, low_threshold=2, high_threshold=4)
    assert result["low"]["count"] == result["high"]["count"] == 2


def test_token_frequencies_normalize_punctuation_and_stopwords() -> None:
    reviews = [Review(review_id="R", product_id="P", rating=5, review_text="맛있어요! 맛있어요 그리고 신선해요", review_date=date(2026, 1, 1), source="x")]
    assert token_frequencies(reviews)["맛있어요"] == 2
