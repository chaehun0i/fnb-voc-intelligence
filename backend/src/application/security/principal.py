"""인증 공급자와 무관한 요청자의 업무 범위입니다."""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    HQ_ADMIN = "HQ_ADMIN"
    QA_MANAGER = "QA_MANAGER"
    OPS_MANAGER = "OPS_MANAGER"
    STORE_MANAGER = "STORE_MANAGER"
    REVIEWER = "REVIEWER"
    AUDITOR = "AUDITOR"


@dataclass(frozen=True)
class Principal:
    principal_id: str
    tenant_id: str
    roles: frozenset[Role]
    store_scope: frozenset[str] = frozenset()
    authentication_source: str = "local"

    def __post_init__(self) -> None:
        if not self.principal_id.strip() or not self.tenant_id.strip():
            raise ValueError("요청자와 조직 식별자가 필요합니다.")
        object.__setattr__(self, "roles", frozenset(Role(r) for r in self.roles))
        object.__setattr__(self, "store_scope", frozenset(self.store_scope))


@dataclass(frozen=True)
class RequestContext:
    principal: Principal
    request_id: str
    correlation_id: str


class AccessError(Exception):
    """안전한 오류 코드만 API에 전달합니다."""

    def __init__(self, code: str = "AUTHORIZATION_DENIED", status: int = 403):
        self.code = code
        self.status = status
        super().__init__(code)
