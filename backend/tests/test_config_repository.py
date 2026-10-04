"""메모리 어댑터도 조직 격리·추가 전용·충돌 의미를 보존합니다."""
from datetime import UTC, datetime

import pytest

from src.application.ports.config_repository import ConfigVersionConflict
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def test_append_history_conflict_and_transaction_rollback():
    persistence = AccessPersistence(InMemoryIncidentRepository())
    first = ConfigVersion(1, "a", RuntimeConfig(), "초기 설정", "admin", datetime(2026, 10, 4, tzinfo=UTC))
    with persistence.transaction("a") as uow:
        assert uow.configs.current() is None
        assert uow.configs.append(first, 0) == first
        with pytest.raises(ConfigVersionConflict):
            uow.configs.append(first, 0)
    with persistence.transaction("b") as uow:
        assert uow.configs.get(1) is None
        assert uow.configs.history(10, 0) == []
    with pytest.raises(RuntimeError), persistence.transaction("a") as uow:
        uow.configs.append(ConfigVersion(2, "a", RuntimeConfig(max_tool_calls=10), "변경", "admin", first.created_at, 1), 1)
        raise RuntimeError("저장 실패")
    with persistence.transaction("a") as uow:
        assert uow.configs.current() == first
        assert uow.configs.history(10, 0) == [first]
