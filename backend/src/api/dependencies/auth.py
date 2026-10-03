"""사용자 헤더의 조직·역할을 신뢰하지 않고 인증 경계를 거칩니다."""

from fastapi import Request

from src.application.security.principal import RequestContext


def request_context(request: Request) -> RequestContext:
    principal = request.app.state.identity_provider.resolve(
        request.headers.get("Authorization")
    )
    return RequestContext(principal, request.state.request_id, request.state.request_id)
