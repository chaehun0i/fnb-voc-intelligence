"""Incident·승인 저장이 하나라도 실패하면 함께 되돌립니다."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass

import psycopg

from src.infrastructure.data_intake import IntakeRepository
from src.infrastructure.jobs.config_events import ConfigEvents
from src.infrastructure.repositories.agent_run_repository import (
    MemoryAgentRunRepository,
    PostgresAgentRunRepository,
)
from src.infrastructure.repositories.approval_repository import (
    MemoryAccessState,
    MemoryApprovalRepository,
    PostgresApprovalRepository,
)
from src.infrastructure.repositories.audit_repository import (
    MemoryAuditRepository,
    PostgresAuditRepository,
)
from src.infrastructure.repositories.config_repository import (
    MemoryConfigRepository,
    PostgresConfigRepository,
)
from src.infrastructure.repositories.decision_repository import (
    MemoryDecisionRepository,
    PostgresDecisionRepository,
)
from src.infrastructure.repositories.execution_repository import ExecutionRepository
from src.infrastructure.repositories.idempotency_repository import (
    MemoryIdempotencyRepository,
    PostgresIdempotencyRepository,
)
from src.infrastructure.repositories.job_repository import (
    MemoryJobRepository,
    PostgresJobRepository,
)
from src.infrastructure.repositories.llm_call_repository import (
    MemoryLLMCallRepository,
    PostgresLLMCallRepository,
)
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.infrastructure.repositories.product_event_repository import (
    ProductEventRepository,
)
from src.infrastructure.repositories.scoped_incident_repository import (
    ScopedIncidentRepository,
)


@dataclass(kw_only=True)
class AccessUnitOfWork:
    incidents: object
    approvals: object
    audit: object
    idempotency: object
    connection: object = None
    jobs: object = None
    configs: object = None
    config_events: object = None
    decisions: object = None
    llm_calls: object = None
    agent_runs: object = None
    executions: object = None
    intake: object = None
    product_events: object = None


class AccessPersistence:
    def __init__(self, incidents):
        self.incidents = incidents
        self.memory = MemoryAccessState()

    @contextmanager
    def transaction(self, tenant_id):
        if isinstance(self.incidents, PostgresIncidentRepository):
            with psycopg.connect(self.incidents.dsn) as connection:
                connection.execute("SET LOCAL lock_timeout='2s'")
                repo = PostgresIncidentRepository(self.incidents.dsn, connection)
                work = AccessUnitOfWork(
                    incidents=ScopedIncidentRepository(repo, tenant_id),
                    approvals=PostgresApprovalRepository(connection, tenant_id),
                    audit=PostgresAuditRepository(connection, tenant_id),
                    idempotency=PostgresIdempotencyRepository(connection, tenant_id),
                    connection=connection,
                    jobs=PostgresJobRepository(connection, tenant_id),
                    configs=PostgresConfigRepository(connection, tenant_id),
                    config_events=ConfigEvents(tenant_id, connection=connection),
                    decisions=PostgresDecisionRepository(connection, tenant_id),
                    llm_calls=PostgresLLMCallRepository(connection, tenant_id),
                    agent_runs=PostgresAgentRunRepository(connection, tenant_id),
                )
                work.executions = ExecutionRepository(work, self.memory, tenant_id)
                work.intake = IntakeRepository(tenant_id, self.memory, connection)
                work.product_events = ProductEventRepository(tenant_id, self.memory, connection)
                yield work
        else:
            with self.incidents._lock, self.memory.lock:
                incidents = deepcopy(self.incidents._items)
                records = deepcopy(self.memory.data)
                try:
                    work = AccessUnitOfWork(
                        incidents=ScopedIncidentRepository(self.incidents, tenant_id),
                        approvals=MemoryApprovalRepository(self.memory, tenant_id),
                        audit=MemoryAuditRepository(self.memory, tenant_id),
                        idempotency=MemoryIdempotencyRepository(self.memory, tenant_id),
                        jobs=MemoryJobRepository(self.memory, tenant_id),
                        configs=MemoryConfigRepository(self.memory, tenant_id),
                        config_events=ConfigEvents(tenant_id, state=self.memory),
                        decisions=MemoryDecisionRepository(self.memory, tenant_id),
                        llm_calls=MemoryLLMCallRepository(self.memory, tenant_id),
                        agent_runs=MemoryAgentRunRepository(self.memory, tenant_id),
                    )
                    work.executions = ExecutionRepository(work, self.memory, tenant_id)
                    work.intake = IntakeRepository(tenant_id, self.memory)
                    work.product_events = ProductEventRepository(tenant_id, self.memory)
                    yield work
                except Exception:
                    self.incidents._items = incidents
                    self.memory.data = records
                    raise
