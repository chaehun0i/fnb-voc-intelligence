"""Validated domain models for product and review records."""

from datetime import date

from pydantic import BaseModel, Field, field_validator


class RequiredTextModel(BaseModel):
    """Shared normalization for required text fields."""

    @field_validator("*", mode="before")
    @classmethod
    def strip_required_strings(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class Product(RequiredTextModel):
    product_id: str
    brand: str
    product_name: str
    category: str
    price: float = Field(ge=0)
    weight_g: float = Field(ge=0)
    calories_kcal: float = Field(ge=0)
    protein_g: float = Field(ge=0)
    carbohydrate_g: float = Field(ge=0)
    sugar_g: float = Field(ge=0)
    fat_g: float = Field(ge=0)
    sodium_mg: float = Field(ge=0)
    source: str


class Review(RequiredTextModel):
    review_id: str
    product_id: str
    rating: int = Field(ge=1, le=5)
    review_text: str
    review_date: date
    source: str

    @field_validator("review_text")
    @classmethod
    def validate_review_text(cls, value: str) -> str:
        if len(value) < 2:
            raise ValueError("must be at least 2 characters")
        return value
