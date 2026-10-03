"""로컬 인증과 미래 운영 인증 경계를 구분합니다."""

import pytest

from src.application.security.principal import AccessError, Principal, Role
from src.infrastructure.auth.local_identity_provider import LocalIdentityProvider


def test_registered_token_maps_server_owned_scope():
    principal = Principal("reviewer", "tenant-a", frozenset({Role.REVIEWER}))
    provider = LocalIdentityProvider({"test-token": principal})
    assert provider.resolve("Bearer test-token") == principal
    with pytest.raises(AccessError) as error:
        provider.resolve("Bearer invented-token")
    assert error.value.code == "INVALID_CREDENTIALS"


def test_missing_authentication_and_production_local_auth_are_rejected():
    with pytest.raises(AccessError) as error:
        LocalIdentityProvider().resolve(None)
    assert error.value.status == 401
    with pytest.raises(RuntimeError):
        LocalIdentityProvider(environment="production")
    with pytest.raises(ValueError):
        Principal("", "tenant-a", frozenset())
