"""동일 Job 실행 식별자와 조직별 이력 분리를 확인합니다."""
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domain.workflows.models import AgentRun, WorkflowState
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def sample_run():
    rid, wid = str(uuid4()), str(uuid4())
    state = WorkflowState(tenant_id="a", incident_id="incident", workflow_id=wid,
        agent_run_id=rid, risk_level="MEDIUM", route="GENERAL_INVESTIGATION", config_version=1)
    return AgentRun(agent_run_id=rid, tenant_id="a", incident_id="incident", workflow_id=wid,
        job_id="job", correlation_id="correlation", config_version=1, jev_decision_id=str(uuid4()),
        started_at=datetime(2026, 10, 5, tzinfo=UTC), state=state)


def test_repository_tenant_dedupe_and_snapshot():
    persistence = AccessPersistence(InMemoryIncidentRepository())
    run = sample_run()
    with persistence.transaction("a") as uow:
        assert uow.agent_runs.save(run) == run
        assert uow.agent_runs.save(run) == run
        assert uow.agent_runs.by_job("job") == run
        assert uow.agent_runs.history("incident") == [run]
        with pytest.raises(ValueError):
            uow.agent_runs.save(run.model_copy(update={"config_version": 2}))
    with persistence.transaction("b") as uow:
        assert uow.agent_runs.get(run.agent_run_id) is None
        assert uow.agent_runs.history("incident") == []
