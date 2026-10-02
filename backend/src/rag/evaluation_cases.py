"""Versioned, deterministic evaluation-case contract."""

from pydantic import BaseModel, Field, field_validator


class EvaluationCase(BaseModel):
    case_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    query: str = Field(min_length=1)
    expected_pain_points: list[str] = Field(default_factory=list)
    relevant_review_ids: list[str] = Field(default_factory=list)
    answer_requirements: list[str] = Field(default_factory=list)
    expected_no_answer: bool = False

    @field_validator(
        "case_id",
        "version",
        "query",
        "expected_pain_points",
        "relevant_review_ids",
        "answer_requirements",
    )
    @classmethod
    def strip_and_require_unique(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            if not (normalized := value.strip()):
                raise ValueError("must not be blank")
            return normalized
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("items must be nonblank and unique")
        return normalized
