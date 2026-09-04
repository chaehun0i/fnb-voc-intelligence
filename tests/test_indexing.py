from datetime import date
from types import SimpleNamespace

import pytest

from src.data.models import Review
from src.rag import indexing
from src.rag.embeddings import FakeEmbeddingProvider


def make_review(review_id: str, text: str) -> Review:
    return Review(
        review_id=review_id,
        product_id="P1",
        rating=3,
        review_text=text,
        review_date=date(2026, 9, 4),
        source="test",
    )


@pytest.fixture
def memory_repository(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], object]:
    stored: dict[tuple[str, str], object] = {}

    def fake_get(_cursor: object, review_id: str, model: str) -> object | None:
        return stored.get((review_id, model))

    def fake_upsert(
        _cursor: object,
        review_id: str,
        vector: list[float],
        model: str,
        content_hash: str,
    ) -> bool:
        key = (review_id, model)
        previous = stored.get(key)
        if previous and previous.content_hash == content_hash:
            return False
        stored[key] = SimpleNamespace(
            embedding=vector,
            content_hash=content_hash,
            dimension=len(vector),
        )
        return True

    monkeypatch.setattr(indexing, "get_review_embedding", fake_get)
    monkeypatch.setattr(indexing, "upsert_review_embedding", fake_upsert)
    return stored


def test_batch_indexing_is_repeatable_and_skips_unchanged_content(
    memory_repository: dict[tuple[str, str], object],
) -> None:
    reviews = [
        make_review("R1", "달아서 좋아요"),
        make_review("R2", "가격이 비싸요"),
        make_review("R3", "양이 적어요"),
    ]
    provider = FakeEmbeddingProvider(dimension=4)
    assert indexing.index_reviews(None, reviews, provider, batch_size=2) == (
        indexing.IndexingReport(indexed=3)
    )
    assert indexing.index_reviews(None, reviews, provider, batch_size=2) == (
        indexing.IndexingReport(skipped=3)
    )
    assert len(memory_repository) == 3


def test_batch_indexing_updates_only_changed_content(
    memory_repository: dict[tuple[str, str], object],
) -> None:
    provider = FakeEmbeddingProvider(dimension=3)
    original = [make_review("R1", "기존 리뷰"), make_review("R2", "그대로예요")]
    indexing.index_reviews(None, original, provider, batch_size=10)
    changed = [make_review("R1", "수정된 리뷰"), original[1]]
    assert indexing.index_reviews(None, changed, provider, batch_size=10) == (
        indexing.IndexingReport(indexed=1, skipped=1)
    )


def test_batch_indexing_reports_provider_failures(
    memory_repository: dict[tuple[str, str], object],
) -> None:
    class FailingProvider(FakeEmbeddingProvider):
        def embed_batch(self, texts: object) -> list[list[float]]:
            raise RuntimeError("provider unavailable")

    reviews = [make_review("R1", "첫 리뷰"), make_review("R2", "둘 리뷰")]
    report = indexing.index_reviews(
        None, reviews, FailingProvider(dimension=2), batch_size=2
    )
    assert report == indexing.IndexingReport(failed=2)


def test_batch_indexing_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        indexing.index_reviews(None, [], FakeEmbeddingProvider(), batch_size=0)
