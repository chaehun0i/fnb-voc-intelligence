import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.analysis.pain_points import (
    PainPointCategory,
    PainPointTaxonomy,
    classify_keywords,
    classify_review,
    load_taxonomy,
    normalize_classification_text,
)


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


def test_taxonomy_loader_errors_are_readable(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_taxonomy(tmp_path / "none.json")
    malformed = tmp_path / "bad.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        load_taxonomy(malformed)


def test_classification_normalization_is_stable() -> None:
    assert normalize_classification_text("  포장이!  눌렸어요. ") == "포장이 눌렸어요"


def test_keyword_classifier_returns_evidence() -> None:
    assert classify_keywords("가격이 비싸요", PainPointTaxonomy(version="1", categories=[category()]))[0]["category_id"] == "price"


def test_no_match_review_is_explicitly_unclassified() -> None:
    result = classify_review("R1", "오늘 날씨가 좋네요", PainPointTaxonomy(version="1", categories=[category()]))
    assert result["review_id"] == "R1"
    assert result["score"] == 0 and result["categories"] == [] and result["evidence"] == []
