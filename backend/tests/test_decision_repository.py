from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.application.security.principal import AccessError
from src.infrastructure.repositories.approval_repository import MemoryAccessState
from src.infrastructure.repositories.decision_repository import (
    MemoryDecisionRepository,
    decision_document,
    decision_from_document,
)
from src.routing.engine import JevEngine
from src.routing.models import DecisionRecord
from tests.test_jev_safety import active


def record():
    return DecisionRecord("00000000-0000-0000-0000-000000000001", "tenant", "incident", "job",
        JevEngine().evaluate(active()), "a"*64, datetime(2026,10,4,tzinfo=UTC), 0.1, 1)


def test_decision_repository_is_tenant_scoped_immutable_and_deduplicated():
    state = MemoryAccessState()
    repo = MemoryDecisionRepository(state, "tenant")
    first = record()
    assert decision_from_document(decision_document(first)) == first
    assert repo.append(first) == first
    assert repo.append(replace(first, duration_ms=99)) == first
    assert repo.history("incident") == [first]
    assert MemoryDecisionRepository(state, "other").history("incident") == []
    with pytest.raises(AccessError):
        MemoryDecisionRepository(state, "other").append(first)
