"""Typed pain point taxonomy and deterministic classification primitives."""

from pydantic import BaseModel, Field, field_validator


class PainPointCategory(BaseModel):
    """One versioned, keyword-addressable pain point category."""

    id: str
    name: str
    description: str
    keywords: list[str] = Field(min_length=1)
    examples: list[str] = Field(min_length=1)

    @field_validator("id", "name", "description")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class PainPointTaxonomy(BaseModel):
    version: str
    categories: list[PainPointCategory] = Field(min_length=1)

    @field_validator("categories")
    @classmethod
    def unique_ids(cls, value: list[PainPointCategory]) -> list[PainPointCategory]:
        if len({category.id for category in value}) != len(value):
            raise ValueError("category ids must be unique")
        return value
