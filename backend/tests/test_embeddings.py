import pytest

from src.rag.embeddings import FakeEmbeddingProvider


def test_fake_embedding_is_deterministic_and_normalized() -> None:
    provider = FakeEmbeddingProvider(dimension=4)
    first = provider.embed("맛있는 음료")
    second = provider.embed("맛있는 음료")
    assert first == second
    assert len(first) == 4
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_fake_embedding_batch_matches_single_embedding() -> None:
    provider = FakeEmbeddingProvider(dimension=3, model="test-model")
    texts = ["달아요", "비싸요"]
    assert provider.embed_batch(texts) == [provider.embed(text) for text in texts]
    assert provider.model == "test-model"
    assert provider.embed(texts[0]) != provider.embed(texts[1])


def test_fake_embedding_rejects_invalid_dimension() -> None:
    with pytest.raises(ValueError, match="dimension"):
        FakeEmbeddingProvider(dimension=0)
