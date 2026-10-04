"""예외 종류를 안정적인 오류 코드와 사용자 안내로 변환합니다."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.application.dashboard.models import (
    DashboardUnavailable,
    InvalidDashboardWindow,
)
from src.application.incidents.service import IncidentNotFound
from src.application.jobs.queries import JobNotFound
from src.application.ports.config_repository import (
    ConfigNotFound,
    ConfigVersionConflict,
    SettingsUnavailable,
)
from src.application.ports.decision_repository import DecisionsUnavailable
from src.application.ports.incident_repository import IncidentConflict
from src.application.ports.job_repository import JobConflict
from src.application.security.principal import AccessError
from src.domain.config.resolution import ConfigValidationFailed
from src.domain.incidents.transitions import DomainRuleViolation
from src.domain.jobs.models import JobRuleViolation


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    details: list[dict] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": details or []},
            "request_id": request.state.request_id,
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DecisionsUnavailable)
    async def decisions_unavailable(request: Request, _: DecisionsUnavailable):
        return error_response(request, 503, "DECISIONS_UNAVAILABLE", "판단 기록 저장소를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.")

    @app.exception_handler(ConfigValidationFailed)
    async def config_validation(request: Request, exc: ConfigValidationFailed):
        return error_response(request, 422, "CONFIG_VALIDATION_FAILED", "설정의 안전 범위와 승인 정책을 확인해 주세요.", exc.details)

    @app.exception_handler(ConfigVersionConflict)
    async def config_conflict(request: Request, _: ConfigVersionConflict):
        return error_response(request, 409, "VERSION_CONFLICT", "다른 운영자가 설정을 변경했습니다. 최신 설정을 다시 불러와 주세요.")

    @app.exception_handler(ConfigNotFound)
    async def config_missing(request: Request, _: ConfigNotFound):
        return error_response(request, 404, "NOT_FOUND", "현재 조직에서 복원할 설정 버전을 찾을 수 없습니다.")

    @app.exception_handler(SettingsUnavailable)
    async def settings_unavailable(request: Request, _: SettingsUnavailable):
        return error_response(request, 503, "SETTINGS_UNAVAILABLE", "운영 설정 저장소를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")

    @app.exception_handler(DashboardUnavailable)
    async def dashboard_unavailable(request: Request, _: DashboardUnavailable) -> JSONResponse:
        return error_response(request, 503, "DASHBOARD_UNAVAILABLE", "현재 운영 현황을 조회할 수 없습니다. 잠시 후 다시 불러와 주세요.")

    @app.exception_handler(InvalidDashboardWindow)
    async def dashboard_window(request: Request, _: InvalidDashboardWindow) -> JSONResponse:
        return error_response(request, 422, "VALIDATION_ERROR", "Dashboard 조회 기간은 7d를 사용해 주세요.")

    @app.exception_handler(JobNotFound)
    async def job_not_found(request: Request, _: JobNotFound) -> JSONResponse:
        return error_response(request, 404, "NOT_FOUND", "작업을 찾을 수 없습니다.")

    @app.exception_handler(JobConflict)
    async def job_conflict(request: Request, _: JobConflict) -> JSONResponse:
        return error_response(request, 409, "CONFLICT", "작업 상태가 변경되었습니다. 최신 정보를 다시 불러와 주세요.")

    @app.exception_handler(JobRuleViolation)
    async def job_rule(request: Request, exc: JobRuleViolation) -> JSONResponse:
        return error_response(request, 409, exc.code, "현재 상태에서는 처리할 수 없습니다. 실행 중인 작업의 중단은 지원하지 않습니다.")

    @app.exception_handler(AccessError)
    async def access_error(request: Request, exc: AccessError) -> JSONResponse:
        message = (
            "로그인이 필요합니다. 인증 설정을 확인해 주세요."
            if exc.status == 401
            else "현재 역할 또는 매장 범위에서는 이 작업을 수행할 수 없습니다."
        )
        message = {
            "IDEMPOTENCY_CONFLICT": "같은 요청 키에 다른 내용이 전달되었습니다. 내용을 확인해 주세요.",
            "PROCESSING": "같은 요청을 처리 중입니다. 잠시 후 동일한 키로 다시 시도해 주세요.",
            "IDEMPOTENCY_KEY_REQUIRED": "중복 실행을 방지하는 요청 키가 필요합니다.",
            "REVIEW_COMMAND_REQUIRED": "승인·반려는 결정 사유와 승인 버전을 포함한 Review 명령으로 진행해 주세요.",
            "VALIDATION_ERROR": "요청 키 형식을 확인해 주세요.",
        }.get(exc.code, message)
        return error_response(request, exc.status, exc.code, message)

    @app.exception_handler(IncidentNotFound)
    async def not_found(request: Request, _: IncidentNotFound) -> JSONResponse:
        return error_response(request, 404, "NOT_FOUND", "인시던트를 찾을 수 없습니다.")

    @app.exception_handler(DomainRuleViolation)
    async def domain_error(request: Request, _: DomainRuleViolation) -> JSONResponse:
        return error_response(
            request,
            409,
            "DOMAIN_RULE_VIOLATION",
            "현재 단계 또는 선행 조건을 확인해 주세요.",
        )

    @app.exception_handler(IncidentConflict)
    async def conflict(request: Request, _: IncidentConflict) -> JSONResponse:
        return error_response(
            request, 409, "CONFLICT", "최신 정보를 다시 불러와 주세요."
        )

    @app.exception_handler(RequestValidationError)
    async def validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in item["loc"]), "type": item["type"]}
            for item in exc.errors()
        ]
        return error_response(
            request,
            422,
            "VALIDATION_ERROR",
            "입력값과 필수 항목을 확인해 주세요.",
            details,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "요청한 API 경로와 메서드를 확인해 주세요.",
        )
