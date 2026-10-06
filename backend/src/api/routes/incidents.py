"""HTTP 입력을 받아 업무 판단을 애플리케이션 서비스에 전달합니다."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from src.api.dependencies.auth import request_context
from src.application.incidents.commands import IncidentCommands
from src.application.incidents.service import IncidentService
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import CorrectiveAction, Evidence, RootCauseCandidate

from ..mappers import incident_response
from ..schemas.incidents import (
    ActionRequest,
    CommandRequest,
    CreateIncidentRequest,
    EvidenceRequest,
    IncidentResponse,
    RcaRequest,
    ReopenRequest,
    TriageRequest,
    VerificationRequest,
    WorkspaceResponse,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


def get_service(request: Request) -> IncidentService:
    return IncidentCommands(
        request.app.state.service, request.app.state.access_persistence,
        request_context(request),
    )


Service = Annotated[IncidentService, Depends(get_service)]


@router.get("", response_model=list[IncidentResponse])
def list_incidents(
    service: Service,
    status: IncidentStatus | None = None,
    severity: Severity | None = None,
    store: str | None = None,
) -> list[IncidentResponse]:
    return [incident_response(item) for item in service.list(status, severity, store)]


@router.post("", response_model=IncidentResponse, status_code=201)
def create_incident(body: CreateIncidentRequest, service: Service) -> IncidentResponse:
    return incident_response(
        service.create(
            title=body.title,
            severity=body.severity,
            store=body.store,
            owner=body.owner,
            sla_due_at=body.sla_due_at.isoformat() if body.sla_due_at else None,
            priority=body.priority,
        )
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str, service: Service) -> IncidentResponse:
    return incident_response(service.get(incident_id))


@router.get("/{incident_id}/workspace", response_model=WorkspaceResponse)
def get_workspace(incident_id: str, service: Service) -> dict:
    return service.workspace(incident_id)


@router.post("/{incident_id}/triage", response_model=IncidentResponse)
def triage(incident_id: str, body: TriageRequest, service: Service) -> IncidentResponse:
    return incident_response(
        service.triage(
            incident_id,
            body.severity,
            body.occurred_at.isoformat() if body.occurred_at else None,
            body.expected_version,
        )
    )


@router.post("/{incident_id}/investigate", response_model=IncidentResponse)
def investigate(
    incident_id: str, body: CommandRequest, service: Service
) -> IncidentResponse:
    return incident_response(service.investigate(incident_id, body.expected_version))


@router.post("/{incident_id}/evidence", response_model=IncidentResponse)
def evidence(
    incident_id: str, body: EvidenceRequest, service: Service
) -> IncidentResponse:
    return incident_response(
        service.add_evidence(
            incident_id,
            Evidence(**body.evidence.model_dump()),
            body.expected_version,
        )
    )


@router.post("/{incident_id}/rca", response_model=IncidentResponse)
def rca(incident_id: str, body: RcaRequest, service: Service) -> IncidentResponse:
    return incident_response(
        service.prepare_rca(
            incident_id,
            [RootCauseCandidate(**item.model_dump()) for item in body.candidates],
            body.expected_version,
        )
    )


@router.post("/{incident_id}/actions", response_model=IncidentResponse)
def actions(
    incident_id: str, body: ActionRequest, service: Service
) -> IncidentResponse:
    return incident_response(
        service.propose_action(
            incident_id,
            [CorrectiveAction(**item.model_dump()) for item in body.actions],
            body.expected_version,
        )
    )


@router.post("/{incident_id}/request-approval", response_model=IncidentResponse)
def request_approval(
    incident_id: str, body: CommandRequest, service: Service
) -> IncidentResponse:
    return incident_response(
        service.request_approval(incident_id, body.expected_version)
    )


@router.post("/{incident_id}/approve", response_model=IncidentResponse)
def approve(
    incident_id: str, body: CommandRequest, service: Service
) -> IncidentResponse:
    return incident_response(service.approve(incident_id, body.expected_version))


@router.post("/{incident_id}/reject", response_model=IncidentResponse)
def reject(
    incident_id: str, body: CommandRequest, service: Service
) -> IncidentResponse:
    return incident_response(service.reject(incident_id, body.expected_version))


@router.post("/{incident_id}/execute", response_model=IncidentResponse)
def execute(
    incident_id: str, body: CommandRequest, service: Service
) -> IncidentResponse:
    return incident_response(service.execute(incident_id, body.expected_version))


@router.post("/{incident_id}/verify", response_model=IncidentResponse)
def verify(
    incident_id: str, body: VerificationRequest, service: Service
) -> IncidentResponse:
    return incident_response(
        service.verify(
            incident_id,
            body.result,
            body.summary,
            body.expected_version,
        )
    )


@router.post("/{incident_id}/close", response_model=IncidentResponse)
def close(incident_id: str, body: CommandRequest, service: Service) -> IncidentResponse:
    return incident_response(service.close(incident_id, body.expected_version))


@router.post("/{incident_id}/reopen", response_model=IncidentResponse)
def reopen(incident_id: str, body: ReopenRequest, service: Service) -> IncidentResponse:
    return incident_response(
        service.reopen(incident_id, body.reason, body.expected_version)
    )
