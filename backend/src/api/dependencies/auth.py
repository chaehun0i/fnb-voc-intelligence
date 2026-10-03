"""사용자 헤더의 조직·역할을 신뢰하지 않고 인증 경계를 거칩니다."""

import re

from fastapi import Request

from src.application.security.principal import AccessError, RequestContext


def request_context(request: Request) -> RequestContext:
    principal = request.app.state.identity_provider.resolve(
        request.headers.get("Authorization")
    )
    key = request.headers.get("Idempotency-Key")
    if key is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", key):
        raise AccessError("VALIDATION_ERROR", 422)
    return RequestContext(principal, request.state.request_id, request.state.request_id, key)
