"""Traceable response contracts for grounded RAG answers."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .search_models import MetadataValue, RetrievalMode


class RagSource(BaseModel):
    review_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_rank: int | None = Field(default=None, ge=1)
    match_source: Literal["lexical", "vector", "both"] | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class RagRetrievalMetadata(BaseModel):
    mode: RetrievalMode
    top_k: int = Field(ge=1)
    retrieved_count: int = Field(ge=0)
    context_count: int = Field(ge=0)


class RagAnswer(BaseModel):
    answer: str = Field(min_length=1)
    status: Literal["success", "no_results", "insufficient_evidence"]
    sources: list[RagSource] = Field(default_factory=list)
    retrieval: RagRetrievalMetadata
    generator_model: str | None = None
    prompt_version: str

    @model_validator(mode="after")
    def validate_success_sources(self) -> "RagAnswer":
        if self.status == "success" and not self.sources:
            raise ValueError("successful answer requires sources")
        return self
