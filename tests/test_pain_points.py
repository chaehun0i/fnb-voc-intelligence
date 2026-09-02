import json
from pathlib import Path

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


def test_initial_taxonomy_has_unique_required_categories() -> None:
    path = Path(__file__).parents[1] / "src" / "analysis" / "taxonomy_v1.json"
    taxonomy = PainPointTaxonomy.model_validate(json.loads(path.read_text(encoding="utf-8")))
    assert {"quality", "taste", "price", "quantity", "packaging", "delivery", "freshness", "service", "usability"} == {item.id for item in taxonomy.categories}
