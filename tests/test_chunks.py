from pathlib import Path

from src.ingestion.chunks import iter_record_chunks


def test_chunked_jsonl_ingestion_keeps_bounded_batches(tmp_path: Path) -> None:
    path = tmp_path / "reviews.jsonl"
    path.write_text('{"id":"1"}\n{"id":"2"}\n{"id":"3"}\n', encoding="utf-8")
    assert [[record.external_id for record in chunk] for chunk in iter_record_chunks(path, "jsonl", "s", 2)] == [["1", "2"], ["3"]]
