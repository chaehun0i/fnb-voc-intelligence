"""실행 시작 API 없이 명시적 Job 실행 결과만 조회합니다."""
from fastapi import APIRouter, Query, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.agent_runs import AgentRunDetailResponse, AgentRunHistoryResponse
from src.application.workflows.queries import AgentRunQueries

router = APIRouter(prefix="/api/v1/incidents", tags=["history-agent-runs"])


def query(request):
    return AgentRunQueries(request.app.state.access_persistence, request_context(request).principal)


@router.get("/{incident_id}/agent-runs", response_model=AgentRunHistoryResponse)
def history(incident_id: str, request: Request, limit: int = Query(20, ge=1, le=100),
            offset: int = Query(0, ge=0, le=10000)):
    return query(request).execute(incident_id, limit=limit, offset=offset)


@router.get("/{incident_id}/agent-runs/{agent_run_id}", response_model=AgentRunDetailResponse)
def detail(incident_id: str, agent_run_id: str, request: Request):
    return query(request).execute(incident_id, run_id=agent_run_id)
