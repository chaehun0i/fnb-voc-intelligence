from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.ingestion.models import IngestionResult, Provenance, RawRecord, SourceConfig


def test_ingestion_contracts_validate() -> None:
    assert SourceConfig(name="partner", kind="csv").name == "partner"
    assert RawRecord(values={"id": "1"}, source="partner", row_number=1).row_number == 1
    assert Provenance(
        source="partner", retrieved_at=datetime(2026, 9, 15, tzinfo=UTC)
    ).source == "partner"
    assert IngestionResult(input_count=1, accepted_count=1, rejected_count=0, duplicate_count=0).accepted_count == 1


def test_ingestion_contracts_reject_invalid_values() -> None:
    with pytest.raises(ValidationError):
        SourceConfig(name="", kind="csv")
    with pytest.raises(ValidationError):
        RawRecord(values={}, source="source", row_number=0)
