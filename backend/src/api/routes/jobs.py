"""HTTP 변환만 담당하며 조직과 역할은 Application에서 검사합니다."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies.auth import request_context
from src.api.schemas.jobs import JobResponse
from src.application.jobs.queries import JobQueries
from src.domain.jobs.models import JobPriority, JobStatus

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def dependencies(request: Request):
    return request.app.state.access_persistence, request_context(request)


Context = Annotated[tuple, Depends(dependencies)]


@router.get("", response_model=list[JobResponse])
def list_jobs(context: Context, status: JobStatus | None = None, priority: JobPriority | None = None,
              job_type: str | None = Query(None, max_length=100), incident_id: str | None = Query(None, max_length=200),
              correlation_id: str | None = Query(None, max_length=200),
              limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
    persistence, request = context
    with persistence.transaction(request.principal.tenant_id) as uow:
        return JobQueries(uow.jobs, request.principal).list(status=status, priority=priority,
            job_type=job_type, incident_id=incident_id, correlation_id=correlation_id, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, context: Context):
    persistence, request = context
    with persistence.transaction(request.principal.tenant_id) as uow:
        return JobQueries(uow.jobs, request.principal).get(job_id)
