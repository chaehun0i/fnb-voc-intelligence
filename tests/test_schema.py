from src.data.schema import (
    PRODUCTS_TABLE_SQL,
    REVIEWS_TABLE_SQL,
    TAXONOMY_CATEGORIES_TABLE_SQL,
    TAXONOMY_KEYWORDS_TABLE_SQL,
)


def test_products_schema_matches_product_constraints() -> None:
    assert "product_id TEXT PRIMARY KEY" in PRODUCTS_TABLE_SQL
    assert "price >= 0" in PRODUCTS_TABLE_SQL


def test_reviews_schema_has_fk_and_rating_constraint() -> None:
    assert "REFERENCES products(product_id)" in REVIEWS_TABLE_SQL
    assert "rating BETWEEN 1 AND 5" in REVIEWS_TABLE_SQL


def test_taxonomy_schema_has_versioned_unique_category_and_keywords() -> None:
    assert "PRIMARY KEY (taxonomy_version, category_id)" in TAXONOMY_CATEGORIES_TABLE_SQL
    assert "REFERENCES taxonomy_categories" in TAXONOMY_KEYWORDS_TABLE_SQL
