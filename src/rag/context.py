"""Structured, deterministic evidence context for RAG."""

from typing import Literal

from pydantic import BaseModel, Field

from .search_models import MetadataValue, SearchResult


class RagContextItem(BaseModel):
    review_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    product_id: str | None = None
    category: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    rank: int = Field(ge=1)
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_rank: int | None = Field(default=None, ge=1)
    match_source: Literal["lexical", "vector", "both"] | None = None
    retrieval_metadata: dict[str, MetadataValue] = Field(default_factory=dict)


class RagContext(BaseModel):
    items: list[RagContextItem] = Field(default_factory=list)


def build_rag_context(results: list[SearchResult]) -> RagContext:
    items = []
    for result in sorted(results, key=lambda item: (item.rank, item.review_id)):
        raw_pain_points = result.metadata.get("pain_points", [])
        if isinstance(raw_pain_points, str):
            pain_points = [raw_pain_points]
        elif isinstance(raw_pain_points, list):
            pain_points = raw_pain_points
        else:
            pain_point = result.metadata.get("pain_point")
            pain_points = [pain_point] if isinstance(pain_point, str) else []
        items.append(
            RagContextItem(
                review_id=result.review_id,
                text=result.text,
                product_id=_string_metadata(result, "product_id"),
                category=_string_metadata(result, "category"),
                pain_points=pain_points,
                rank=result.rank,
                lexical_rank=result.lexical_rank,
                vector_rank=result.vector_rank,
                match_source=result.match_source,
                retrieval_metadata=result.metadata,
            )
        )
    return RagContext(items=items)


def _string_metadata(result: SearchResult, key: str) -> str | None:
    value = result.metadata.get(key)
    return value if isinstance(value, str) else None
