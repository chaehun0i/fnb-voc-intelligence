"""Jev는 Shadow로 유지하며 명시적 권한·Config 조건만 실행을 허용합니다."""
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.agents.history import HistoryWorkflows, WorkflowNotAllowed
from src.application.security.principal import Principal, RequestContext, Role
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Evidence, Incident
from src.domain.jobs.models import Job
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)
from src.routing.shadow import ShadowDecisions


def setup_history():
    now = datetime(2026, 10, 5, tzinfo=UTC)
    incident = Incident("i", "INC-1", "quality", Severity.MEDIUM, IncidentStatus.INVESTIGATING,
        "store", "owner", now.isoformat(), now.isoformat(), tenant_id="t",
        evidence=[Evidence("e", "source", "HISTORY", "참조", .9)])
    persistence = AccessPersistence(InMemoryIncidentRepository([incident]))
    config = RuntimeConfig(jev_enabled=True, auto_investigation=True, allowed_tools=("voc.search",))
    with persistence.transaction("t") as uow:
        uow.configs.append(ConfigVersion(1, "t", config, "초기", "admin", now), 0)
    decision = ShadowDecisions(persistence, clock=lambda: now).record(
        Job("snapshot", "t", "incident.snapshot", "c", now, now, incident_id="i", store="store"))
    context = RequestContext(Principal("operator", "t", frozenset({Role.OPS_MANAGER})), "request", "correlation")
    return persistence, HistoryWorkflows(persistence, lambda: now), context, decision


def test_opt_in_dedupe_and_immutable_config_snapshot():
    persistence, service, context, decision = setup_history()
    assert not persistence.memory.data.get("agent_runs")
    first = service.enqueue(context, "i", decision.decision_id)
    assert service.enqueue(context, "i", decision.decision_id) == first
    run, resolved, _ = service.prepare(first)
    with persistence.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1,
                                  config=RuntimeConfig()), 1)
    restored, snapshot, _ = service.prepare(first)
    assert restored == run and snapshot == resolved and restored.config_version == 1


def test_history_not_selected_or_disabled_is_rejected():
    persistence, service, context, decision = setup_history()
    with persistence.transaction("t") as uow:
        incident = uow.incidents.get("i")
        uow.incidents.save(replace(incident, status=IncidentStatus.CLOSED))
    with pytest.raises(WorkflowNotAllowed):
        service.enqueue(context, "i", decision.decision_id)


def test_new_execution_cannot_reuse_disabled_historical_policy():
    persistence, service, context, decision = setup_history()
    with persistence.transaction("t") as uow:
        version = uow.configs.current()
        uow.configs.append(replace(version, config_version=2, parent_version=1,
                                  config=RuntimeConfig()), 1)
    with pytest.raises(WorkflowNotAllowed):
        service.enqueue(context, "i", decision.decision_id)
