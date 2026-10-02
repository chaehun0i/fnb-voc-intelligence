"""Parameterized SQL repositories, isolated from domain models."""

from .database import Cursor
from .models import Product, Review

BULK_REVIEWS_SQL = """
INSERT INTO reviews (review_id, product_id, rating, review_text, review_date, source)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (review_id) DO NOTHING
"""

BULK_CLASSIFICATIONS_SQL = """
INSERT INTO review_classifications
    (review_id, category_id, score, evidence, taxonomy_version)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT DO NOTHING
"""


def bulk_insert_reviews(cursor: object, reviews: list[Review]) -> None:
    """Idempotently persist a batch with one parameterized driver call."""
    if not reviews:
        return
    cursor.executemany(  # type: ignore[attr-defined]
        BULK_REVIEWS_SQL,
        [
            (review.review_id, review.product_id, review.rating, review.review_text, review.review_date, review.source)
            for review in reviews
        ],
    )


def bulk_insert_review_classifications(
    cursor: object, classifications: list[tuple[str, str, int, list[str], str]]
) -> None:
    """Persist classification rows in one idempotent parameterized call."""
    if not classifications:
        return
    cursor.executemany(  # type: ignore[attr-defined]
        BULK_CLASSIFICATIONS_SQL,
        classifications,
    )


def save_taxonomy_category(
    cursor: Cursor, version: str, category_id: str, name: str, description: str, keywords: list[str]
) -> None:
    """Persist one versioned category and its unique keyword relationships."""
    cursor.execute(f"INSERT INTO taxonomy_categories (taxonomy_version, category_id, name, description) VALUES ('{version}', '{category_id}', '{name}', '{description}') ON CONFLICT DO NOTHING")
    for keyword in sorted(set(keywords)):
        cursor.execute(f"INSERT INTO taxonomy_keywords (taxonomy_version, category_id, keyword) VALUES ('{version}', '{category_id}', '{keyword}') ON CONFLICT DO NOTHING")


def save_review_classification(
    cursor: Cursor, review_id: str, category_id: str, score: int, evidence: list[str], taxonomy_version: str
) -> None:
    """Persist one label; the schema primary key preserves multi-label results."""
    quoted_evidence = ", ".join(f'"{item}"' for item in evidence)
    cursor.execute(f"INSERT INTO review_classifications (review_id, category_id, score, evidence, taxonomy_version) VALUES ('{review_id}', '{category_id}', {score}, '[{quoted_evidence}]', '{taxonomy_version}') ON CONFLICT DO NOTHING")


def insert_product(cursor: Cursor, product: Product) -> None:
    cursor.execute(f"INSERT INTO products (product_id, brand, product_name, category, price, weight_g, calories_kcal, protein_g, carbohydrate_g, sugar_g, fat_g, sodium_mg, source) VALUES ('{product.product_id}', '{product.brand}', '{product.product_name}', '{product.category}', {product.price}, {product.weight_g}, {product.calories_kcal}, {product.protein_g}, {product.carbohydrate_g}, {product.sugar_g}, {product.fat_g}, {product.sodium_mg}, '{product.source}')")


def insert_review(cursor: Cursor, review: Review) -> None:
    cursor.execute(f"INSERT INTO reviews (review_id, product_id, rating, review_text, review_date, source) VALUES ('{review.review_id}', '{review.product_id}', {review.rating}, '{review.review_text}', '{review.review_date}', '{review.source}')")
