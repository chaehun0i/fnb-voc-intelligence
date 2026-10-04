"""공개 생성 대신 Job 원본의 Shadow 이력만 조회합니다."""
from fastapi import APIRouter, Query, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.decisions import DecisionHistoryResponse, DecisionResponse
from src.application.decisions.queries import DecisionQueries

router = APIRouter(prefix="/api/v1/incidents", tags=["shadow-decisions"])


def query(request):
    principal = request_context(request).principal
    return DecisionQueries(request.app.state.access_persistence, principal)


@router.get("/{incident_id}/decisions", response_model=DecisionHistoryResponse)
def history(incident_id: str, request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    return query(request).history(incident_id, limit, offset)


@router.get("/{incident_id}/decisions/latest", response_model=DecisionResponse | None)
def latest(incident_id: str, request: Request):
    return query(request).latest(incident_id)
