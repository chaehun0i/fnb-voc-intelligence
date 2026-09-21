"""Reproducible metadata for scale datasets."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class DatasetManifest(BaseModel):
    source: str = Field(min_length=1)
    version: str = Field(min_length=1)
    row_count: int = Field(ge=0)
    checksum: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def updated_after_created(cls, value: datetime, info: object) -> datetime:
        created_at = info.data.get("created_at")
        if created_at is not None and value < created_at:
            raise ValueError("updated_at must not precede created_at")
        return value
