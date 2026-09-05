"""Validated contracts shared by all retrieval modes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RetrievalMode = Literal["lexical", "vector", "hybrid"]
MetadataValue = str | int | float | bool | None


class SearchFilters(BaseModel):
    model_config = ConfigDict(frozen=True)

    product_id: str | None = None
    category: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    pain_point: str | None = None


class SearchQuery(BaseModel):
    text: str
    mode: RetrievalMode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=100)
    candidate_k: int = Field(default=20, ge=1, le=1000)
    filters: SearchFilters = Field(default_factory=SearchFilters)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_candidate_size(self) -> "SearchQuery":
        if self.candidate_k < self.top_k:
            raise ValueError("candidate_k must be greater than or equal to top_k")
        return self


class SearchResult(BaseModel):
    review_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    rank: int = Field(ge=1)
    mode: RetrievalMode
    lexical_score: float | None = Field(default=None, ge=0)
    vector_score: float | None = None
    fused_score: float | None = Field(default=None, ge=0)
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_rank: int | None = Field(default=None, ge=1)
    match_source: Literal["lexical", "vector", "both"] | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_score_presence(self) -> "SearchResult":
        if all(
            score is None
            for score in (self.lexical_score, self.vector_score, self.fused_score)
        ):
            raise ValueError("at least one retrieval score is required")
        if self.mode == "hybrid":
            if self.fused_score is None or self.match_source is None:
                raise ValueError("hybrid results require fused score and match source")
            if self.match_source in ("lexical", "both") and self.lexical_rank is None:
                raise ValueError("lexical match source requires lexical_rank")
            if self.match_source in ("vector", "both") and self.vector_rank is None:
                raise ValueError("vector match source requires vector_rank")
        return self
