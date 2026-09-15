from src.ingestion.adapters import FakeSourceAdapter
from src.ingestion.models import RawRecord, SourceConfig


def test_fake_adapter_is_deterministic_for_records_and_normalization() -> None:
    record = RawRecord(external_id="x", values={"name": "tea"}, source="fake", row_number=1)
    adapter = FakeSourceAdapter([record], SourceConfig(name="fake", kind="fake"))
    assert list(adapter.read()) == [record]
    assert adapter.normalize(record) == {"name": "tea"}
    assert adapter.provenance(record).external_id == "x"
