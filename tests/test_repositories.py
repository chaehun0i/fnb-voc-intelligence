from src.data.repositories import save_review_classification, save_taxonomy_category


class RecordingCursor:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def execute(self, query: str) -> None:
        self.queries.append(query)


def test_taxonomy_repository_persists_unique_keywords() -> None:
    cursor = RecordingCursor()
    save_taxonomy_category(cursor, "1.0", "price", "가격", "설명", ["비싸", "비싸"])
    assert len(cursor.queries) == 2


def test_classification_repository_preserves_score_evidence_and_version() -> None:
    cursor = RecordingCursor()
    save_review_classification(cursor, "R1", "price", 2, ["비싸"], "1.0")
    assert "score" in cursor.queries[0] and "1.0" in cursor.queries[0]
