"""실제 승인 기록과 Incident 변경의 일관성을 확인합니다."""

from dataclasses import replace

import pytest

from src.api.app import demo_incidents
from src.domain.approvals.models import Approval
from src.domain.incidents.enums import Severity
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def approval():
    return Approval("approval-1", "legacy-local", "demo-incident", ("action-1",),
                    "digest", 1, Severity.HIGH, "requester", "2026-10-01T09:00:00Z",
                    "2026-10-02T09:00:00Z")


def test_scoped_approval_save_get_and_transaction_rollback():
    repo = InMemoryIncidentRepository(demo_incidents())
    persistence = AccessPersistence(repo)
    with persistence.transaction("legacy-local") as uow:
        assert uow.approvals.save(approval()).version == 1
    with persistence.transaction("other") as uow:
        assert uow.approvals.list() == []
        assert uow.approvals.get("approval-1") is None
    with pytest.raises(RuntimeError), persistence.transaction("legacy-local") as uow:
        item = uow.incidents.get("demo-incident")
        uow.incidents.save(replace(item, owner="변경"))
        uow.approvals.save(replace(approval(), status="APPROVED"))
        raise RuntimeError("저장 실패 재현")
    assert repo.get("demo-incident").owner == "운영 담당자"
    with persistence.transaction("legacy-local") as uow:
        assert uow.approvals.get("approval-1").status == "PENDING"
