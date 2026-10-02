from datetime import date

from src.data.models import Review
from src.data.repositories import (
    BULK_CLASSIFICATIONS_SQL,
    BULK_REVIEWS_SQL,
    bulk_insert_review_classifications,
    bulk_insert_reviews,
)


class Cursor:
    def __init__(self) -> None:
        self.calls = []

    def executemany(self, query: str, params: list[tuple[object, ...]]) -> None:
        self.calls.append((query, params))


def test_bulk_reviews_use_one_idempotent_call() -> None:
    cursor = Cursor()
    review = Review(
        review_id="R1",
        product_id="P1",
        rating=3,
        review_text="좋아요",
        review_date=date(2026, 1, 1),
        source="test",
    )
    bulk_insert_reviews(cursor, [review, review])
    assert len(cursor.calls) == 1 and "ON CONFLICT" in BULK_REVIEWS_SQL
    assert len(cursor.calls[0][1]) == 2


def test_bulk_classifications_use_one_idempotent_call() -> None:
    cursor = Cursor()
    bulk_insert_review_classifications(cursor, [("R1", "taste", 1, ["짜다"], "1.0")])
    assert len(cursor.calls) == 1
    assert "ON CONFLICT" in BULK_CLASSIFICATIONS_SQL


def test_empty_bulk_operations_do_not_call_database() -> None:
    cursor = Cursor()
    bulk_insert_reviews(cursor, [])
    bulk_insert_review_classifications(cursor, [])
    assert cursor.calls == []
