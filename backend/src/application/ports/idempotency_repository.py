"""완료 결과 재사용과 요청 충돌을 저장 기술에서 분리합니다."""
from typing import Protocol

from src.domain.incidents.models import Incident


class IdempotencyRepository(Protocol):
    def claim(self, principal_id: str, operation: str, key: str, fingerprint: str) -> Incident | None: ...
    def complete(self, principal_id: str, operation: str, key: str, result: Incident) -> None: ...
