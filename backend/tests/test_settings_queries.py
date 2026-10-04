"""조회는 기본값과 저장 버전을 구분하며 조직 밖 이력을 읽지 않습니다."""
from datetime import UTC, datetime

import pytest

from src.application.config.queries import SettingsQueries, config_diff
from src.application.security.principal import Principal, Role
from src.domain.config.models import ConfigVersion, RuntimeConfig
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def test_current_history_read_only_and_tenant_isolated():
    persistence = AccessPersistence(InMemoryIncidentRepository())
    auditor = Principal("audit", "a", frozenset({Role.AUDITOR}))
    queries = SettingsQueries(persistence, auditor)
    assert queries.current()["config"]["version"] == 0
    assert queries.current()["sources"]["max_tool_calls"] == "PLATFORM_DEFAULT"
    assert queries.history()["revisions"] == []
    assert persistence.memory.data == {"approvals": {}}
    with persistence.transaction("a") as uow:
        uow.configs.append(ConfigVersion(1, "a", RuntimeConfig(max_tool_calls=10), "도구 한도 축소", "admin", datetime(2026, 10, 4, tzinfo=UTC)), 0)
    result = queries.current()
    assert result["effective"]["max_tool_calls"] == 10
    assert not result["save_permission"]["allowed"]
    assert result["sources"]["max_tool_calls"] == "TENANT"
    assert queries.history(1)["revisions"][0]["changes"] == [{"field": "max_tool_calls", "before": "20", "after": "10"}]
    assert SettingsQueries(persistence, Principal("b", "b", frozenset({Role.HQ_ADMIN}))).history()["revisions"] == []
    with pytest.raises(ValueError):
        queries.history(101)


def test_diff_uses_typed_fields_and_empty_change():
    assert config_diff(RuntimeConfig(), RuntimeConfig()) == []
