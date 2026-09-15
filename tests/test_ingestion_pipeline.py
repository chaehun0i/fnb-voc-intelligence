from src.ingestion.adapters import FakeSourceAdapter
from src.ingestion.models import RawRecord, SourceConfig
from src.ingestion.pipeline import run_pipeline


def test_pipeline_is_repeatable_and_injectable() -> None:
    adapter = FakeSourceAdapter([RawRecord(values={"id": "A"}, source="f", row_number=1), RawRecord(values={"id": "a"}, source="f", row_number=2)], SourceConfig(name="f", kind="fake"))
    stored: list[str] = []
    records, result = run_pipeline(adapter, lambda value: value["id"], lambda value: value, stored.extend)
    assert records == ["A"] and stored == ["A"] and result.duplicate_count == 1
