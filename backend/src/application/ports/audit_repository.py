"""감사 로그에는 추가와 조직별 조회만 허용합니다."""
from typing import Protocol

from src.domain.approvals.audit import AuditRecord


class AuditRepository(Protocol):
    def append(self, record: AuditRecord) -> None: ...
    def list(self) -> list[AuditRecord]: ...
