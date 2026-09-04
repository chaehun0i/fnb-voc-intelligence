from src.data.schema import (
    PRODUCTS_TABLE_SQL,
    REVIEW_CLASSIFICATIONS_TABLE_SQL,
    REVIEW_EMBEDDINGS_TABLE_SQL,
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


def test_classification_schema_allows_multilabel_with_fks() -> None:
    assert "PRIMARY KEY (review_id, taxonomy_version, category_id)" in REVIEW_CLASSIFICATIONS_TABLE_SQL
    assert "REFERENCES reviews(review_id)" in REVIEW_CLASSIFICATIONS_TABLE_SQL


def test_review_embedding_schema_preserves_vector_provenance() -> None:
    assert "embedding vector NOT NULL" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "REFERENCES reviews(review_id)" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "PRIMARY KEY (review_id, model)" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "vector_dims(embedding) = dimension" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "content_hash CHAR(64)" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "created_at TIMESTAMPTZ" in REVIEW_EMBEDDINGS_TABLE_SQL
    assert "updated_at TIMESTAMPTZ" in REVIEW_EMBEDDINGS_TABLE_SQL
