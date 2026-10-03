"""승인 기록은 조직 범위 안에서 조회하고 버전을 확인해 저장합니다."""

from typing import Protocol

from src.domain.approvals.models import Approval


class ApprovalRepository(Protocol):
    def get(self, approval_id: str) -> Approval | None: ...
    def list(self, incident_id: str | None = None) -> list[Approval]: ...
    def save(self, approval: Approval) -> Approval: ...
