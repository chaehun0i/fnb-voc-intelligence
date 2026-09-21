from src.data.repositories import BULK_PRODUCTS_SQL


def test_bulk_product_upsert_preserves_conflict_safety() -> None:
    assert "ON CONFLICT (product_id)" in BULK_PRODUCTS_SQL
