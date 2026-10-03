"""로컬 개발 전용 서버 설정입니다. OIDC 또는 운영 인증이 아닙니다."""

import json
import os

from src.application.security.principal import AccessError, Principal, Role


class LocalIdentityProvider:
    def __init__(
        self, identities: dict[str, Principal] | None = None,
        default: Principal | None = None, *, environment: str = "development",
    ):
        if environment not in {"development", "test"}:
            raise RuntimeError("로컬 인증은 development/test에서만 허용됩니다.")
        self.identities = dict(identities or {})
        self.default = default

    def resolve(self, authorization: str | None) -> Principal:
        if authorization is None and self.default is not None:
            return self.default
        if not authorization:
            raise AccessError("AUTHENTICATION_REQUIRED", 401)
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or token not in self.identities:
            raise AccessError("INVALID_CREDENTIALS", 401)
        return self.identities[token]


def configured_identity_provider() -> LocalIdentityProvider:
    environment = os.getenv("SERVIQ_ENV", "development")
    if os.getenv("SERVIQ_IDENTITY_PROVIDER", "local") != "local":
        raise RuntimeError("OIDC 공급자는 아직 연결되지 않았습니다.")
    configured = os.getenv("SERVIQ_LOCAL_IDENTITIES")
    if configured is not None:
        values = json.loads(configured)
        identities = {
            token: Principal(**value) for token, value in values.items()
            if token.strip()
        }
        if not identities or len(identities) != len(values):
            raise ValueError("로컬 인증 설정에 유효한 계정이 필요합니다.")
        return LocalIdentityProvider(identities, environment=environment)
    # 기존 로컬 실행·회귀 테스트를 위한 서버 고정 계정입니다.
    default = Principal("local-operator", "legacy-local", frozenset({Role.HQ_ADMIN}))
    return LocalIdentityProvider(default=default, environment=environment)
