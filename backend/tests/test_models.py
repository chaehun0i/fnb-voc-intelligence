from datetime import date

import pytest
from pydantic import ValidationError

from src.data import Product, Review


def product_data() -> dict[str, object]:
    return {"product_id": "P001", "brand": "가상푸드", "product_name": "든든 도시락", "category": "도시락", "price": 5900, "weight_g": 350, "calories_kcal": 520, "protein_g": 20, "carbohydrate_g": 65, "sugar_g": 8, "fat_g": 15, "sodium_mg": 900, "source": "synthetic"}


def review_data() -> dict[str, object]:
    return {"review_id": "R001", "product_id": "P001", "rating": 5, "review_text": "맛있어요", "review_date": date(2026, 8, 1), "source": "synthetic"}


def test_valid_models_normalize_text() -> None:
    assert Product(**product_data()).brand == "가상푸드"
    assert Review(**review_data()).review_text == "맛있어요"


@pytest.mark.parametrize("field,value", [("brand", "  "), ("price", -1)])
def test_product_rejects_blank_or_negative(field: str, value: object) -> None:
    data = product_data()
    data[field] = value
    with pytest.raises(ValidationError):
        Product(**data)


@pytest.mark.parametrize("field,value", [("rating", 0), ("rating", 6), ("review_text", " x ")])
def test_review_rejects_invalid_values(field: str, value: object) -> None:
    data = review_data()
    data[field] = value
    with pytest.raises(ValidationError):
        Review(**data)
