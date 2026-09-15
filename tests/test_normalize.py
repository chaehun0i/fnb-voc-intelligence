from src.ingestion.normalize import deduplicate


def test_deduplication_is_stable() -> None:
    assert deduplicate([" A ", "a", "B"], lambda value: value) == ([" A ", "B"], 1)
