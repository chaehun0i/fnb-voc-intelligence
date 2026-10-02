from .enums import IncidentStatus
from .models import Incident, StateTransition

class DomainRuleViolation(ValueError): pass

_NEXT={IncidentStatus.DETECTED:IncidentStatus.TRIAGED,IncidentStatus.TRIAGED:IncidentStatus.INVESTIGATING,IncidentStatus.INVESTIGATING:IncidentStatus.RCA_READY,IncidentStatus.RCA_READY:IncidentStatus.ACTION_PROPOSED,IncidentStatus.ACTION_PROPOSED:IncidentStatus.PENDING_APPROVAL,IncidentStatus.PENDING_APPROVAL:IncidentStatus.EXECUTING,IncidentStatus.EXECUTING:IncidentStatus.VERIFYING,IncidentStatus.VERIFYING:IncidentStatus.RESOLVED,IncidentStatus.RESOLVED:IncidentStatus.CLOSED}
def transition(incident:Incident, target:IncidentStatus, occurred_at:str)->Incident:
    if incident.status is IncidentStatus.CLOSED: raise DomainRuleViolation("closed incident cannot transition")
    if target is IncidentStatus.REOPENED and incident.verification and incident.verification.result=="FAIL":
        incident.status=target; incident.timeline.append(StateTransition(target,occurred_at)); return incident
    if _NEXT.get(incident.status)!=target: raise DomainRuleViolation("invalid incident status transition")
    if target is IncidentStatus.EXECUTING and not incident.approved: raise DomainRuleViolation("approval is required")
    if target is IncidentStatus.RESOLVED and (not incident.verification or incident.verification.result!="PASS"): raise DomainRuleViolation("verification PASS is required")
    incident.status=target; incident.timeline.append(StateTransition(target,occurred_at)); return incident
