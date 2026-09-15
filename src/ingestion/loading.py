"""Safe PostgreSQL loading for normalized external records."""

from dataclasses import dataclass

from src.data.models import Product, Review
from src.data.repositories import bulk_insert_reviews, insert_product


@dataclass(frozen=True)
class LoadResult:
    products: int
    reviews: int
    dry_run: bool


def load_records(
    connection: object,
    products: list[Product],
    reviews: list[Review],
    *,
    dry_run: bool = False,
) -> LoadResult:
    """Validate review foreign keys, then persist products before reviews."""
    product_ids = {product.product_id for product in products}
    orphan = next((review.product_id for review in reviews if review.product_id not in product_ids), None)
    if orphan is not None:
        raise ValueError(f"orphan product_id: {orphan}")
    if dry_run:
        return LoadResult(len(products), len(reviews), True)
    cursor = connection.cursor()  # type: ignore[attr-defined]
    for product in products:
        insert_product(cursor, product)
    bulk_insert_reviews(cursor, reviews)
    connection.commit()  # type: ignore[attr-defined]
    return LoadResult(len(products), len(reviews), False)
