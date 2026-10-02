"""테스트 주입과 로컬 개발 설정을 지원하는 HTTP 진입점입니다."""

import os
import re
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import register_error_handlers
from src.api.routes.incidents import router
from src.application.incidents.service import IncidentService
from src.application.ports.incident_repository import IncidentRepository
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident, StateTransition
from src.infrastructure.repositories.in_memory_incident_repository import (
    InMemoryIncidentRepository,
)


def demo_incidents() -> list[Incident]:
    """실제 데이터와 구분되는 고정 시각의 개발 예시입니다."""
    occurred_at = "2026-10-01T09:00:00+00:00"
    return [
        Incident(
            id="demo-incident",
            display_id="INC-DEMO-001",
            title="냉장 진열 온도 이상 확인",
            severity=Severity.HIGH,
            status=IncidentStatus.DETECTED,
            store="데모 매장",
            owner="운영 담당자",
            created_at=occurred_at,
            sla_due_at="2026-10-02T09:00:00+00:00",
            timeline=[StateTransition(IncidentStatus.DETECTED, occurred_at)],
        )
    ]


def configured_repository() -> IncidentRepository:
    """저장 방식은 환경으로 선택하며 스키마 준비는 별도 명령으로 실행합니다."""
    mode = os.getenv("SERVIQ_REPOSITORY", "memory")
    if mode == "memory":
        return InMemoryIncidentRepository()
    if mode == "postgres":
        from src.infrastructure.repositories.postgres_incident_repository import (
            PostgresIncidentRepository,
        )

        dsn = os.getenv("SERVIQ_DATABASE_URL")
        if not dsn:
            raise RuntimeError("SERVIQ_DATABASE_URL을 설정해 주세요.")
        return PostgresIncidentRepository(dsn)
    raise RuntimeError("SERVIQ_REPOSITORY는 memory 또는 postgres여야 합니다.")


def create_app(
    repository: IncidentRepository | None = None,
    clock: Callable[[], datetime] | None = None,
    id_generator: Callable[[], str] | None = None,
    *,
    seed_demo: bool = False,
) -> FastAPI:
    app = FastAPI(title="ServIQ API", version="0.4.1")
    repo = repository if repository is not None else configured_repository()
    if seed_demo:
        for item in demo_incidents():
            if repo.get(item.id) is None:
                repo.save(item)
    app.state.service = IncidentService(repo, clock=clock, id_generator=id_generator)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = (
            supplied
            if re.fullmatch(r"[A-Za-z0-9._-]{1,80}", supplied)
            else str(uuid4())
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    register_error_handlers(app)
    app.include_router(router)

    @app.get("/api/v1/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app(seed_demo=os.getenv("SERVIQ_SEED_DEMO", "false").lower() == "true")
