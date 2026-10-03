"""승인 원본의 조회를 조직 범위에 제한합니다."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.reviews import ReviewApprovalResponse, ReviewResponse
from src.application.approvals.queries import ReviewQueries
from src.application.commands.incidents import IncidentCommands

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


def get_queries(request: Request):
    context = request_context(request)
    return request.app.state.access_persistence, IncidentCommands(
        request.app.state.service, request.app.state.access_persistence, context), context


Queries = Annotated[tuple, Depends(get_queries)]


@router.get("", response_model=list[ReviewApprovalResponse])
def list_reviews(queries: Queries, status: Literal["PENDING", "APPROVED", "REJECTED"] | None = None,
                 limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    persistence, commands, context = queries
    with persistence.transaction(context.principal.tenant_id) as uow:
        return ReviewQueries(commands._service(uow.incidents), uow.approvals, context).list(status, limit, offset)


@router.get("/{approval_id}", response_model=ReviewResponse)
def get_review(approval_id: str, queries: Queries):
    persistence, commands, context = queries
    with persistence.transaction(context.principal.tenant_id) as uow:
        return ReviewQueries(commands._service(uow.incidents), uow.approvals, context).get(approval_id)
