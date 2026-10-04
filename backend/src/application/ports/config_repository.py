"""설정 버전의 저장 기술과 무관한 조회·추가 계약입니다."""
from typing import Protocol

from src.domain.config.models import ConfigVersion


class ConfigVersionConflict(Exception):
    pass


class ConfigNotFound(Exception):
    pass


class SettingsUnavailable(Exception):
    pass


class ConfigRepository(Protocol):
    def current(self) -> ConfigVersion | None: ...
    def get(self, version: int) -> ConfigVersion | None: ...
    def history(self, limit: int, offset: int) -> list[ConfigVersion]: ...
    def append(self, version: ConfigVersion, expected_version: int) -> ConfigVersion: ...
