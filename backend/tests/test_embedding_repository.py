from datetime import UTC, datetime
from typing import Any

from src.data.embedding_repository import (
    GET_REVIEW_EMBEDDING_SQL,
    UPSERT_REVIEW_EMBEDDING_SQL,
    get_review_embedding,
    upsert_review_embedding,
)


class MemoryEmbeddingCursor:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], tuple[Any, ...]] = {}
        self.result: tuple[Any, ...] | None = None
        self.last_query = ""
        self.last_params: tuple[Any, ...] = ()

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self.last_query = query
        self.last_params = params or ()
        if query == UPSERT_REVIEW_EMBEDDING_SQL:
            review_id, model, dimension, vector, content_hash = self.last_params
            key = (review_id, model)
            previous = self.rows.get(key)
            if previous and previous[4] == content_hash and previous[2] == dimension:
                self.result = None
                return
            now = datetime.now(UTC)
            created_at = previous[5] if previous else now
            self.rows[key] = (
                review_id,
                model,
                dimension,
                vector,
                content_hash,
                created_at,
                now,
            )
            self.result = (review_id,)
        elif query == GET_REVIEW_EMBEDDING_SQL:
            self.result = self.rows.get((self.last_params[0], self.last_params[1]))

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.result


def test_review_embedding_round_trip_and_unchanged_skip() -> None:
    cursor = MemoryEmbeddingCursor()
    assert upsert_review_embedding(cursor, "R1", [0.1, 0.2], "fake-v1", "a" * 64)
    assert not upsert_review_embedding(
        cursor, "R1", [9.0, 9.0], "fake-v1", "a" * 64
    )
    stored = get_review_embedding(cursor, "R1", "fake-v1")
    assert stored is not None
    assert stored.embedding == [0.1, 0.2]
    assert stored.content_hash == "a" * 64


def test_review_embedding_updates_changed_content() -> None:
    cursor = MemoryEmbeddingCursor()
    upsert_review_embedding(cursor, "R1", [0.1, 0.2], "fake-v1", "a" * 64)
    assert upsert_review_embedding(cursor, "R1", [0.3, 0.4], "fake-v1", "b" * 64)
    stored = get_review_embedding(cursor, "R1", "fake-v1")
    assert stored is not None
    assert stored.embedding == [0.3, 0.4]
    assert stored.content_hash == "b" * 64


def test_repository_uses_bound_parameters() -> None:
    cursor = MemoryEmbeddingCursor()
    model = "unsafe' model"
    upsert_review_embedding(cursor, "R1", [1.0], model, "a" * 64)
    assert model not in cursor.last_query
    assert model in cursor.last_params
