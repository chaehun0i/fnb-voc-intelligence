"""저장 기술과 무관하게 인시던트를 조회하고 저장하는 계약입니다."""

from typing import Protocol

from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident


class IncidentConflict(ValueError):
    """다른 명령이 먼저 저장해 최신 버전을 다시 읽어야 합니다."""


class IncidentRepository(Protocol):
    def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        store: str | None = None,
        *, tenant_id: str | None = None,
    ) -> list[Incident]: ...

    def get(self, incident_id: str, *, tenant_id: str | None = None) -> Incident | None: ...

    def save(self, incident: Incident) -> Incident:
        """버전을 확인하고 저장한 새 버전의 복사본을 반환합니다."""
        ...
