"""조직·역할·매장 범위를 한 곳에서 검증합니다."""

from src.application.security.principal import AccessError, Principal, Role

ROLE_ACTIONS = {
    "read": frozenset(Role),
    "operate": frozenset({Role.HQ_ADMIN, Role.QA_MANAGER, Role.OPS_MANAGER,
                           Role.STORE_MANAGER}),
    "review": frozenset({Role.HQ_ADMIN, Role.REVIEWER}),
    "admin": frozenset({Role.HQ_ADMIN}),
}


def allowed(principal: Principal, action: str, store: str | None = None) -> bool:
    return bool(principal.roles & ROLE_ACTIONS[action]) and (
        store is None or not principal.store_scope or store in principal.store_scope
    ) and not (
        Role.STORE_MANAGER in principal.roles
        and Role.HQ_ADMIN not in principal.roles
        and store is not None and store not in principal.store_scope
    )


def require(principal: Principal, action: str, store: str | None = None) -> None:
    if not allowed(principal, action, store):
        raise AccessError()
