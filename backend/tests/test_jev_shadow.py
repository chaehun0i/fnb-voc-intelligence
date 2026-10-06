from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import psycopg

from src.application.decisions.shadow import ShadowDecisions
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.domain.decisions.models import DecisionReasonCode
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.domain.jobs.models import Job
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.jobs.runtime import snapshot_processor
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def setup_shadow(engine=None):
    now = datetime(2026,10,4,tzinfo=UTC)
    incident = Incident("i", "INC-1", "고객 이름 email secret 원문", Severity.MEDIUM, IncidentStatus.DETECTED, "s", "owner", now.isoformat(), now.isoformat(), tenant_id="t")
    repo = InMemoryIncidentRepository([incident])
    persistence = AccessPersistence(repo)
    with persistence.transaction("t") as uow:
        uow.configs.append(ConfigVersion(1, "t", RuntimeConfig(jev_enabled=True), "초기", "admin", now), 0)
    job = Job("j", "t", "incident.snapshot", "c", now, now, incident_id="i", store="s")
    shadow = ShadowDecisions(persistence, engine=engine, clock=lambda: now)
    return repo, persistence, job, shadow


def test_shadow_is_deduplicated_and_does_not_change_business_state():
    repo, persistence, job, shadow = setup_shadow()
    before = repo.get("i")
    first = shadow.record(job)
    assert shadow.record(job) == first
    assert first.result.config_version == 1
    assert repo.get("i") == before
    assert len(persistence.memory.data["audit"]) == 1
    assert "email" not in str(persistence.memory.data["decisions"])
    snapshot_processor(repo, shadow)(job)
    assert repo.get("i") == before
    with persistence.transaction("t") as uow:
        current = uow.configs.current()
        uow.configs.append(replace(current, config_version=2, parent_version=1, config=RuntimeConfig(jev_enabled=True, parallelism=1)), 1)
    assert shadow.record(job) == first and first.result.config_version == 1
    assert len(persistence.memory.data["audit"]) == 1


def test_shadow_failure_is_explicit_safe_and_isolated(caplog):
    engine = Mock()
    engine.evaluate.side_effect = RuntimeError("provider credential secret")
    repo, persistence, job, shadow = setup_shadow(engine)
    first = shadow.record(job)
    assert first.error_code == "DECISION_INTERNAL_ERROR"
    assert first.result.investigation_agents == () and not first.result.requires_llm
    assert DecisionReasonCode.ENGINE_FAILURE in first.result.reason_codes
    assert "secret" not in caplog.text
    assert repo.get("i").status == IncidentStatus.DETECTED
    assert persistence.memory.data["audit"][0].result == "FAILED"
    assert shadow.record(job) == first
    with persistence.transaction("t") as uow:
        current = uow.configs.current()
        uow.configs.append(replace(current, config_version=2, parent_version=1, config=RuntimeConfig()), 1)
    assert shadow.record(replace(job, job_id="off")) is None


def test_persistence_failure_logs_safe_failure_without_incident_mutation(monkeypatch, caplog):
    repo, persistence, job, shadow = setup_shadow()
    before = repo.get("i")
    def unavailable(_tenant):
        raise psycopg.OperationalError("secret credential")
    monkeypatch.setattr(persistence, "transaction", unavailable)
    snapshot_processor(repo, shadow)(job)
    assert repo.get("i") == before
    assert "DECISION_PERSISTENCE_UNAVAILABLE" in caplog.text and "secret" not in caplog.text
    assert not persistence.memory.data.get("decisions")
