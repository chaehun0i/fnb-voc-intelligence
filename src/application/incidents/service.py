from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.transitions import transition


class IncidentNotFound(LookupError): pass
class IncidentService:
 def __init__(self,repo): self.repo=repo
 def list(self,**filters): return self.repo.list(**filters)
 def get(self,incident_id):
  item=self.repo.get(incident_id)
  if not item: raise IncidentNotFound(incident_id)
  return item
 def triage(self,incident_id,severity,occurred_at):
  item=self.get(incident_id)
  if severity: item.severity=Severity(severity)
  transition(item,IncidentStatus.TRIAGED,occurred_at)
  return self.repo.save(item)
