"""Read-only data quality summaries."""

from collections import Counter
from statistics import median

from .models import Product, Review


def product_quality(products: list[Product]) -> dict[str, object]:
    prices = [product.price for product in products]
    identifiers = [product.product_id for product in products]
    return {"row_count": len(products), "duplicate_product_ids": duplicates(identifiers), "null_rates": {}, "invalid_prices": sum(price < 0 for price in prices), "price": {"min": min(prices, default=None), "max": max(prices, default=None), "median": median(prices) if prices else None}, "category_distribution": dict(Counter(product.category for product in products))}


def review_quality(reviews: list[Review], products: list[Product]) -> dict[str, object]:
    texts = [review.review_text for review in reviews]
    product_ids = {product.product_id for product in products}
    return {"row_count": len(reviews), "duplicate_review_ids": duplicates([review.review_id for review in reviews]), "null_rates": {}, "rating_distribution": dict(Counter(review.rating for review in reviews)), "empty_review_count": sum(not text.strip() for text in texts), "review_text_length": {"min": min(map(len, texts), default=None), "median": median(map(len, texts)) if texts else None, "max": max(map(len, texts), default=None)}, "orphan_product_ids": [review.product_id for review in reviews if review.product_id not in product_ids]}


def duplicates(values: list[str]) -> list[str]:
    return sorted(value for value, count in Counter(values).items() if count > 1)
