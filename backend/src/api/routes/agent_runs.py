"""실행 시작 API 없이 명시적 Job 실행 결과만 조회합니다."""
from typing import Literal

import psycopg
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from src.ai.ax.service import AgentRunQueries
from src.api.dependencies.auth import request_context
from src.api.schemas.agent_runs import AgentRunDetailResponse, AgentRunHistoryResponse
from src.application.agent_controls import AgentControls
from src.application.ports.repositories import AgentRunsUnavailable

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


class AgentControlInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(strict=True, ge=0)


class AgentControlResponse(BaseModel):
    control_status: Literal["RUNNING", "PAUSED", "STOPPED", "MANUAL_TAKEOVER"]


@router.post("/{incident_id}/agent-runs/{agent_run_id}/controls/{action}", response_model=AgentControlResponse)
def control(incident_id: str, agent_run_id: str, action: Literal["pause", "resume", "stop", "takeover"],
            body: AgentControlInput, request: Request):
    try:
        event = AgentControls(request.app.state.access_persistence).execute(request_context(request),
            incident_id, agent_run_id, action, body.expected_version)
        return {"control_status": event.control}
    except psycopg.Error as error:
        raise AgentRunsUnavailable() from error
