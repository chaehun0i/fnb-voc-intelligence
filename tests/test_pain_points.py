import pytest
from pydantic import ValidationError

from src.analysis.pain_points import PainPointCategory, PainPointTaxonomy


def category() -> PainPointCategory:
    return PainPointCategory(id="price", name="가격", description="가격 관련 불만", keywords=["비싸"], examples=["가격이 비싸요"])


def test_taxonomy_model_validates() -> None:
    assert PainPointTaxonomy(version="1.0", categories=[category()]).categories[0].id == "price"


def test_taxonomy_rejects_blank_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError):
        PainPointCategory(id="", name="가격", description="설명", keywords=["비싸"], examples=["예시"])
    with pytest.raises(ValidationError):
        PainPointTaxonomy(version="1", categories=[category(), category()])
