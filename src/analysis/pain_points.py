"""Typed pain point taxonomy and deterministic classification primitives."""

import json
import re
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from src.data.models import Review


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


def load_taxonomy(path: str | Path) -> PainPointTaxonomy:
    """Load a non-empty, validated taxonomy with readable errors."""
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"taxonomy file not found: {source}")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed taxonomy: {source}") from error
    try:
        return PainPointTaxonomy.model_validate(raw)
    except Exception as error:
        raise ValueError(f"invalid taxonomy: {error}") from error


def normalize_classification_text(text: str) -> str:
    """Normalize punctuation and whitespace while preserving Korean tokens."""
    return re.sub(r"\s+", " ", re.sub(r"[^가-힣A-Za-z0-9\s]", " ", text)).strip().lower()


def classify_keywords(text: str, taxonomy: PainPointTaxonomy) -> list[dict[str, object]]:
    """Return multi-label categories with matched keyword evidence."""
    normalized = normalize_classification_text(text)
    return [{"category_id": category.id, "evidence": evidence} for category in taxonomy.categories if (evidence := [keyword for keyword in category.keywords if keyword.lower() in normalized])]


def score_classification(text: str, taxonomy: PainPointTaxonomy, minimum_score: int = 1) -> list[dict[str, object]]:
    """Score labels by evidence count, with category ID tie ordering."""
    labels = [{**label, "score": len(label["evidence"])} for label in classify_keywords(text, taxonomy)]
    return sorted((label for label in labels if label["score"] >= minimum_score), key=lambda label: (-label["score"], str(label["category_id"])))


def classify_review(review_id: str, text: str, taxonomy: PainPointTaxonomy, minimum_score: int = 1) -> dict[str, object]:
    """Classify one review, explicitly retaining a no-match state."""
    labels = score_classification(text, taxonomy, minimum_score)
    return {"review_id": review_id, "normalized_text": normalize_classification_text(text), "score": max((int(label["score"]) for label in labels), default=0), "categories": [label["category_id"] for label in labels], "evidence": [term for label in labels for term in label["evidence"]]}


def classify_reviews(reviews: list[Review], taxonomy: PainPointTaxonomy, minimum_score: int = 1) -> dict[str, object]:
    """Classify validated reviews in input order and aggregate labels."""
    results = [classify_review(review.review_id, review.review_text, taxonomy, minimum_score) for review in reviews]
    counts = Counter(category for result in results for category in result["categories"])
    total = len(results)
    return {"results": results, "category_counts": dict(sorted(counts.items())), "category_ratios": {key: value / total if total else 0 for key, value in sorted(counts.items())}}
