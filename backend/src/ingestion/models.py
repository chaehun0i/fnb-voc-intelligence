"""Typed, source-independent contracts for ingestion."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SourceConfig(BaseModel):
    name: str = Field(min_length=1)
    kind: Literal["csv", "json", "jsonl", "fake"]
    metadata: dict[str, str] = Field(default_factory=dict)


class RawRecord(BaseModel):
    external_id: str | None = None
    values: dict[str, Any]
    source: str = Field(min_length=1)
    row_number: int = Field(ge=1)


class Provenance(BaseModel):
    source: str = Field(min_length=1)
    external_id: str | None = None
    retrieved_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)


class IngestionResult(BaseModel):
    input_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list)

    @field_validator("accepted_count", "rejected_count", "duplicate_count")
    @classmethod
    def counts_are_nonnegative(cls, value: int) -> int:
        return value
