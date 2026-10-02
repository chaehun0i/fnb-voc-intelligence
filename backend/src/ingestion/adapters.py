"""Provider-neutral source adapter protocol and deterministic fake."""

from collections.abc import Iterable
from typing import Protocol

from .models import Provenance, RawRecord, SourceConfig


class SourceAdapter(Protocol):
    config: SourceConfig

    def read(self) -> Iterable[RawRecord]: ...

    def normalize(self, record: RawRecord) -> dict[str, object]: ...

    def provenance(self, record: RawRecord) -> Provenance: ...


class FakeSourceAdapter:
    def __init__(self, records: list[RawRecord], config: SourceConfig) -> None:
        self.records = records
        self.config = config

    def read(self) -> Iterable[RawRecord]:
        return list(self.records)

    def normalize(self, record: RawRecord) -> dict[str, object]:
        return dict(record.values)

    def provenance(self, record: RawRecord) -> Provenance:
        from datetime import UTC, datetime

        return Provenance(
            source=self.config.name,
            external_id=record.external_id,
            retrieved_at=datetime.now(UTC),
            metadata=self.config.metadata,
        )
