"""PostgreSQL DDL statements for the application schema."""

PRODUCTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY, brand TEXT NOT NULL, product_name TEXT NOT NULL,
    category TEXT NOT NULL, price NUMERIC NOT NULL CHECK (price >= 0),
    weight_g NUMERIC NOT NULL CHECK (weight_g >= 0), calories_kcal NUMERIC NOT NULL CHECK (calories_kcal >= 0),
    protein_g NUMERIC NOT NULL CHECK (protein_g >= 0), carbohydrate_g NUMERIC NOT NULL CHECK (carbohydrate_g >= 0),
    sugar_g NUMERIC NOT NULL CHECK (sugar_g >= 0), fat_g NUMERIC NOT NULL CHECK (fat_g >= 0),
    sodium_mg NUMERIC NOT NULL CHECK (sodium_mg >= 0), source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

REVIEWS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(product_id),
    rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5), review_text TEXT NOT NULL,
    review_date DATE NOT NULL, source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

TAXONOMY_CATEGORIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS taxonomy_categories (
    taxonomy_version TEXT NOT NULL, category_id TEXT NOT NULL, name TEXT NOT NULL,
    description TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (taxonomy_version, category_id)
)
"""

TAXONOMY_KEYWORDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS taxonomy_keywords (
    taxonomy_version TEXT NOT NULL, category_id TEXT NOT NULL, keyword TEXT NOT NULL,
    PRIMARY KEY (taxonomy_version, category_id, keyword),
    FOREIGN KEY (taxonomy_version, category_id)
        REFERENCES taxonomy_categories(taxonomy_version, category_id)
)
"""
