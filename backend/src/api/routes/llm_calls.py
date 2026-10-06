"""호출 생성 API 없이 Incident 범위의 안전한 사용 기록만 조회합니다."""
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from src.ai.intelligence.models import LLMCallRecord
from src.ai.intelligence.service import LLMCallQueries
from src.api.dependencies.auth import request_context

router = APIRouter(prefix="/api/v1/incidents", tags=["llm-usage"])


class LLMCallHistory(BaseModel):
    calls: list[LLMCallRecord]
    limit: int


@router.get("/{incident_id}/llm-calls", response_model=LLMCallHistory)
def history(incident_id: str, request: Request, limit: int = Query(20, ge=1, le=100)):
    principal = request_context(request).principal
    records = LLMCallQueries(request.app.state.access_persistence, principal).history(incident_id, limit)
    return LLMCallHistory(calls=records, limit=limit)
