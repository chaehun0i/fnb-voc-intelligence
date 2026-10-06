"""복원은 현재 안전 정책을 검증한 새 버전이며 과거 row를 바꾸지 않습니다."""
from dataclasses import replace

import pytest

from src.application.config.commands import SettingsCommands
from src.application.ports.repositories import (
    ConfigNotFound,
    ConfigVersionConflict,
)
from src.domain.config.models import RuntimeConfig
from src.domain.config.resolution import ConfigResolver, ConfigValidationFailed
from tests.test_settings_commands import setup_commands


def test_rollback_new_version_lineage_replay_and_cross_tenant():
    persistence, context, commands = setup_commands()
    first = commands.update(RuntimeConfig(), 0, "초기 설정")
    update = SettingsCommands(persistence, replace(context, idempotency_key="update"))
    second = update.update(RuntimeConfig(max_tool_calls=10), 1, "한도 축소")
    rollback = SettingsCommands(persistence, replace(context, idempotency_key="rollback"))
    third = rollback.rollback(1, 2, "초기 한도 복원")
    assert third.config == first.config
    assert third.parent_version == 2 and third.rollback_source == 1 and third.config_version == 3
    assert rollback.rollback(1, 2, "초기 한도 복원") == third
    with persistence.transaction("a") as uow:
        assert uow.configs.get(1) == first
        assert uow.configs.get(2) == second
        assert len(uow.audit.list()) == 3
        assert uow.audit.list()[-1].resource_id.endswith(":rollback:1")
    assert len(persistence.memory.data["config_events"]) == 3
    other = SettingsCommands(persistence, replace(context, principal=replace(context.principal, tenant_id="b")))
    with pytest.raises(ConfigNotFound):
        other.rollback(1, 0, "다른 조직의 버전")


def test_rollback_revalidates_current_caps_and_expected_version():
    persistence, context, commands = setup_commands()
    commands.update(RuntimeConfig(), 0, "초기 설정")
    capped = SettingsCommands(persistence, replace(context, idempotency_key="cap"), ConfigResolver(rules={"max_tool_calls": (1, 10, True)}))
    with pytest.raises(ConfigValidationFailed):
        capped.rollback(1, 1, "새 상한에 맞지 않는 복원")
    with pytest.raises(ConfigVersionConflict):
        SettingsCommands(persistence, replace(context, idempotency_key="stale")).rollback(1, 0, "이전 화면 기준")
    with persistence.transaction("a") as uow:
        assert len(uow.configs.history()) == 1
        assert len(uow.audit.list()) == 1
