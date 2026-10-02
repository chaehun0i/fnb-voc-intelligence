"""저장용 JSON 계약과 API 저장소 선택 경계를 확인합니다."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.api.app import configured_repository
from src.application.incidents.service import IncidentService
from src.domain.incidents.enums import Severity
from src.domain.incidents.models import Evidence
from src.infrastructure.incident_codec import incident_document, incident_from_document
from src.infrastructure.migrations import migration_sql
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)


def test_storage_document_round_trip_and_copy_isolation() -> None:
    service = IncidentService(
        InMemoryIncidentRepository(),
        clock=lambda: datetime(2026, 10, 2, tzinfo=UTC),
        id_generator=lambda: "codec-incident",
    )
    incident = service.create("온도 이탈", Severity.HIGH, "검증 매장", "검증 담당")
    incident = replace(incident, evidence=[Evidence("ev-1", "센서", "온도", "8도", 0.9)])
    document = incident_document(incident)
    assert incident_from_document(document) == incident
    document["evidence"][0]["summary"] = "외부 변경"
    assert incident.evidence[0].summary == "8도"


def test_sql_resource_contains_separate_schema_and_retry_constraints() -> None:
    sql = migration_sql()
    assert "CREATE TABLE IF NOT EXISTS serviq_incidents" in sql
    assert "REFERENCES serviq_incidents(id)" in sql
    assert "CHECK (attempts >= 0)" in sql
    assert "CHECK (max_attempts > 0)" in sql
    assert "DROP TABLE" not in sql


def test_postgres_selection_does_not_connect_during_factory_setup(monkeypatch) -> None:
    monkeypatch.setenv("SERVIQ_REPOSITORY", "postgres")
    monkeypatch.setenv("SERVIQ_DATABASE_URL", "postgresql://synthetic-db/serviq")
    repository = configured_repository()
    assert isinstance(repository, PostgresIncidentRepository)
    assert repository.dsn == "postgresql://synthetic-db/serviq"


def test_invalid_storage_configuration_fails_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("SERVIQ_REPOSITORY", "postgres")
    monkeypatch.delenv("SERVIQ_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="SERVIQ_DATABASE_URL"):
        configured_repository()
    monkeypatch.setenv("SERVIQ_REPOSITORY", "unknown")
    with pytest.raises(RuntimeError, match="memory 또는 postgres"):
        configured_repository()
