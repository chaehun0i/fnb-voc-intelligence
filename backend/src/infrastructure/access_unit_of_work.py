"""Incident·승인 저장이 하나라도 실패하면 함께 되돌립니다."""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass

import psycopg

from src.infrastructure.outbox.config_events import ConfigEvents
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
from src.infrastructure.repositories.idempotency_repository import (
    MemoryIdempotencyRepository,
    PostgresIdempotencyRepository,
)
from src.infrastructure.repositories.job_repository import (
    MemoryJobRepository,
    PostgresJobRepository,
)
from src.infrastructure.repositories.postgres_incident_repository import (
    PostgresIncidentRepository,
)
from src.infrastructure.repositories.scoped_incident_repository import (
    ScopedIncidentRepository,
)


@dataclass
class AccessUnitOfWork:
    incidents: object
    approvals: object
    audit: object
    idempotency: object
    connection: object = None
    jobs: object = None
    configs: object = None
    config_events: object = None


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
                yield AccessUnitOfWork(ScopedIncidentRepository(repo, tenant_id),
                                       PostgresApprovalRepository(connection, tenant_id),
                                       PostgresAuditRepository(connection, tenant_id),
                                       PostgresIdempotencyRepository(connection, tenant_id), connection,
                                       PostgresJobRepository(connection, tenant_id),
                                       PostgresConfigRepository(connection, tenant_id),
                                       ConfigEvents(tenant_id, connection=connection))
        else:
            with self.incidents._lock, self.memory.lock:
                incidents = deepcopy(self.incidents._items)
                records = deepcopy(self.memory.data)
                try:
                    yield AccessUnitOfWork(
                        ScopedIncidentRepository(self.incidents, tenant_id),
                        MemoryApprovalRepository(self.memory, tenant_id),
                        MemoryAuditRepository(self.memory, tenant_id),
                        MemoryIdempotencyRepository(self.memory, tenant_id),
                        jobs=MemoryJobRepository(self.memory, tenant_id),
                        configs=MemoryConfigRepository(self.memory, tenant_id),
                        config_events=ConfigEvents(tenant_id, state=self.memory),
                    )
                except Exception:
                    self.incidents._items = incidents
                    self.memory.data = records
                    raise
