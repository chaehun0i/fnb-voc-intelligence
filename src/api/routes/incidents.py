from fastapi import APIRouter, Request
from ..schemas.incidents import IncidentResponse, TriageRequest
from ..mappers import incident_response
from ..errors import not_found, domain_error
from src.application.incidents.service import IncidentNotFound
from src.domain.incidents.transitions import DomainRuleViolation
router=APIRouter(prefix="/api/v1/incidents",tags=["incidents"])
@router.get("",response_model=list[IncidentResponse])
def list_incidents(request:Request,status:str|None=None,severity:str|None=None,store:str|None=None): return [incident_response(i) for i in request.app.state.service.list(status=status,severity=severity,store=store)]
@router.get("/{incident_id}",response_model=IncidentResponse)
def get_incident(incident_id:str,request:Request):
 try:return incident_response(request.app.state.service.get(incident_id))
 except IncidentNotFound:raise not_found()
@router.post("/{incident_id}/triage",response_model=IncidentResponse)
def triage(incident_id:str,body:TriageRequest,request:Request):
 try:return incident_response(request.app.state.service.triage(incident_id,body.severity,body.occurred_at))
 except IncidentNotFound:raise not_found()
 except DomainRuleViolation:raise domain_error()
