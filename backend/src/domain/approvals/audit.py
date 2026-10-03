"""승인 결정과 별도로 보관하는 불변 실행 이력입니다."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AuditRecord:
    audit_id: str
    tenant_id: str
    principal_id: str
    action: str
    resource_type: str
    resource_id: str
    result: str
    request_id: str
    correlation_id: str
    occurred_at: str
    resulting_version: int | None = None
