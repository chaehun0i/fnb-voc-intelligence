"""향후 검증된 OIDC 공급자를 연결할 인증 경계입니다."""

from typing import Protocol

from src.application.security.principal import Principal


class IdentityProvider(Protocol):
    def resolve(self, authorization: str | None) -> Principal: ...
