"""도메인 모델을 HTTP 응답으로 변환합니다."""

from dataclasses import asdict

from src.domain.incidents.models import Incident

from .schemas.incidents import IncidentResponse


def incident_response(incident: Incident) -> IncidentResponse:
    return IncidentResponse.model_validate(asdict(incident))
