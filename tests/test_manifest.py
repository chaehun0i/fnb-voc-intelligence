from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.ingestion.manifest import DatasetManifest


def test_manifest_validates_reproducible_metadata() -> None:
    now = datetime(2026, 9, 21, tzinfo=UTC)
    manifest = DatasetManifest(source="partner", version="v1", row_count=3, checksum="a" * 64, created_at=now, updated_at=now)
    assert manifest.row_count == 3


def test_manifest_rejects_invalid_checksum() -> None:
    with pytest.raises(ValidationError):
        DatasetManifest(source="partner", version="v1", row_count=0, checksum="bad", created_at=datetime(2026, 9, 21, tzinfo=UTC), updated_at=datetime(2026, 9, 21, tzinfo=UTC))
