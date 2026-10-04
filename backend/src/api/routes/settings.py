"""운영 설정 Route는 HTTP 변환만 담당합니다."""
from fastapi import APIRouter, Query, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.settings import (
    RollbackConfigRequest,
    RuntimeHistoryResponse,
    RuntimeWorkspaceResponse,
    UpdateConfigRequest,
)
from src.application.config.commands import SettingsCommands
from src.application.config.queries import SettingsQueries, workspace
from src.domain.config.models import config_from_document

router = APIRouter(prefix="/api/v1/settings/runtime", tags=["settings"])


def dependencies(request):
    context = request_context(request)
    persistence = request.app.state.access_persistence
    resolver = request.app.state.config_resolver
    return context, SettingsQueries(persistence, context.principal, resolver), SettingsCommands(
        persistence, context, resolver, clock=request.app.state.service.clock)


@router.get("", response_model=RuntimeWorkspaceResponse)
def current_config(request: Request):
    return dependencies(request)[1].current()


@router.get("/history", response_model=RuntimeHistoryResponse)
def config_history(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    return dependencies(request)[1].history(limit, offset)


@router.post("", response_model=RuntimeWorkspaceResponse)
def update_config(body: UpdateConfigRequest, request: Request):
    context, queries, commands = dependencies(request)
    version = commands.update(config_from_document(body.config.model_dump()), body.expected_version, body.reason)
    return workspace(version, context.principal, queries.resolver)


@router.post("/rollback", response_model=RuntimeWorkspaceResponse)
def rollback_config(body: RollbackConfigRequest, request: Request):
    context, queries, commands = dependencies(request)
    version = commands.rollback(body.target_version, body.expected_version, body.reason)
    return workspace(version, context.principal, queries.resolver)
