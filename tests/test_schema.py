from src.data.schema import PRODUCTS_TABLE_SQL


def test_products_schema_matches_product_constraints() -> None:
    assert "product_id TEXT PRIMARY KEY" in PRODUCTS_TABLE_SQL
    assert "price >= 0" in PRODUCTS_TABLE_SQL
