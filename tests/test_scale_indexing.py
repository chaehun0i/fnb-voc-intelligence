from datetime import date
from types import SimpleNamespace

import pytest

from src.data.models import Review
from src.rag import indexing
from src.rag.embeddings import FakeEmbeddingProvider
from src.rag.scale_indexing import index_review_stream


def review(review_id: str) -> Review:
    return Review(
        review_id=review_id,
        product_id="P1",
        rating=3,
        review_text=f"리뷰 {review_id}",
        review_date=date(2026, 9, 14),
        source="test",
    )


@pytest.fixture
def embedding_store(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], object]:
    store: dict[tuple[str, str], object] = {}

    def get(_cursor: object, review_id: str, model: str) -> object | None:
        return store.get((review_id, model))

    def upsert(
        _cursor: object,
        review_id: str,
        vector: list[float],
        model: str,
        content_hash: str,
    ) -> bool:
        key = (review_id, model)
        if key in store and store[key].content_hash == content_hash:
            return False
        store[key] = SimpleNamespace(content_hash=content_hash, dimension=len(vector))
        return True

    monkeypatch.setattr(indexing, "get_review_embedding", get)
    monkeypatch.setattr(indexing, "upsert_review_embedding", upsert)
    return store


def test_stream_indexing_is_incremental_and_idempotent(
    embedding_store: dict[tuple[str, str], object],
) -> None:
    reviews = (review(f"R{number}") for number in range(5))
    provider = FakeEmbeddingProvider(dimension=3)
    assert index_review_stream(None, reviews, provider, batch_size=2) == indexing.IndexingReport(
        indexed=5
    )
    assert len(embedding_store) == 5
    assert index_review_stream(
        None, (review(f"R{number}") for number in range(5)), provider, batch_size=2
    ) == indexing.IndexingReport(skipped=5)


def test_stream_indexing_applies_limit(
    embedding_store: dict[tuple[str, str], object],
) -> None:
    report = index_review_stream(
        None,
        (review(f"R{number}") for number in range(5)),
        FakeEmbeddingProvider(),
        batch_size=2,
        limit=3,
    )
    assert report.indexed == 3
    assert len(embedding_store) == 3
