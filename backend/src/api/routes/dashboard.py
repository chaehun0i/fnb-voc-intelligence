"""HTTP에서 집계 규칙을 계산하지 않습니다."""
from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.dashboard import DashboardResponse

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(request: Request, window: Literal["7d"] = "7d"):
    context = request_context(request)
    return asdict(request.app.state.dashboard_queries.get(context.principal, window))
