"""설정 변경의 중복 실행·권한·버전·감사 계약입니다."""
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from src.application.config.commands import SettingsCommands
from src.application.ports.config_repository import ConfigVersionConflict
from src.application.security.principal import (
    AccessError,
    Principal,
    RequestContext,
    Role,
)
from src.domain.config.models import RuntimeConfig
from src.infrastructure.access_unit_of_work import AccessPersistence
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def setup_commands(role=Role.HQ_ADMIN):
    persistence = AccessPersistence(InMemoryIncidentRepository())
    context = RequestContext(Principal("admin", "a", frozenset({role})), "request", "correlation", "key")
    return persistence, context, SettingsCommands(persistence, context, clock=lambda: datetime(2026, 10, 4, tzinfo=UTC))


def test_update_replay_conflict_audit_event_and_stale_version():
    persistence, context, commands = setup_commands()
    result = commands.update(RuntimeConfig(), 0, "초기 설정")
    assert commands.update(RuntimeConfig(), 0, "초기 설정") == result
    with pytest.raises(AccessError) as error:
        commands.update(RuntimeConfig(max_tool_calls=10), 0, "다른 설정")
    assert error.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(ConfigVersionConflict):
        SettingsCommands(persistence, replace(context, idempotency_key="new")).update(RuntimeConfig(), 0, "이전 화면")
    with persistence.transaction("a") as uow:
        assert len(uow.configs.history()) == 1
        assert len(uow.audit.list()) == 1
        assert uow.audit.list()[0].principal_id == "admin"
    assert len(persistence.memory.data["config_events"]) == 1
    assert "config" not in persistence.memory.data["config_events"][0]


def test_auditor_write_is_denied_and_audited():
    persistence, _, commands = setup_commands(Role.AUDITOR)
    with pytest.raises(AccessError):
        commands.update(RuntimeConfig(), 0, "권한 없는 변경")
    with persistence.transaction("a") as uow:
        assert uow.configs.current() is None
        assert uow.audit.list()[0].result == "DENIED"
