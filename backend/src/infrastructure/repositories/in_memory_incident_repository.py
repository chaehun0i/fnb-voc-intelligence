"""개발과 테스트를 위한 격리된 메모리 인시던트 저장소입니다."""

from copy import deepcopy
from dataclasses import replace
from threading import RLock

from src.application.ports.incident_repository import (
    IncidentConflict,
    IncidentRepository,
)
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident


class InMemoryIncidentRepository(IncidentRepository):
    def __init__(self, items: list[Incident] | None = None) -> None:
        self._lock = RLock()
        self._items = {item.id: deepcopy(item) for item in (items or [])}

    def list(
        self,
        status: IncidentStatus | None = None,
        severity: Severity | None = None,
        store: str | None = None,
    ) -> list[Incident]:
        with self._lock:
            return deepcopy(
                [
                    item
                    for item in self._items.values()
                    if (status is None or item.status == status)
                    and (severity is None or item.severity == severity)
                    and (store is None or item.store == store)
                ]
            )

    def get(self, incident_id: str) -> Incident | None:
        with self._lock:
            return deepcopy(self._items.get(incident_id))

    def save(self, incident: Incident) -> Incident:
        with self._lock:
            previous = self._items.get(incident.id)
            if (previous is None and incident.version != 0) or (
                previous is not None and previous.version != incident.version
            ):
                raise IncidentConflict("인시던트가 변경되었습니다. 다시 읽어 주세요.")
            saved = replace(incident, version=incident.version + 1)
            self._items[saved.id] = deepcopy(saved)
            return deepcopy(saved)
