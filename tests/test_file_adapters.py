from pathlib import Path

from src.ingestion.file_adapters import map_product, map_review, read_file

PRODUCT_MAP = {"product_id": "id", "brand": "brand", "product_name": "name", "category": "category", "price": "price", "weight_g": "weight", "calories_kcal": "calories", "protein_g": "protein", "carbohydrate_g": "carbs", "sugar_g": "sugar", "fat_g": "fat", "sodium_mg": "sodium"}
REVIEW_MAP = {"review_id": "id", "product_id": "product", "rating": "rating", "review_text": "text", "review_date": "date"}


def test_product_csv_mapping(tmp_path: Path) -> None:
    path = tmp_path / "products.csv"
    path.write_text("id,brand,name,category,price,weight,calories,protein,carbs,sugar,fat,sodium\nP1,B,T,C,1,1,1,1,1,1,1,1\n", encoding="utf-8")
    assert map_product(read_file(path, "csv", "partner")[0], PRODUCT_MAP).product_id == "P1"


def test_review_jsonl_mapping_preserves_date_and_id(tmp_path: Path) -> None:
    path = tmp_path / "reviews.jsonl"
    path.write_text('{"id":"R1","product":"P1","rating":5,"text":"좋아요","date":"2026-01-01"}\n', encoding="utf-8")
    assert map_review(read_file(path, "jsonl", "partner")[0], REVIEW_MAP).review_id == "R1"
