from src.application.ports.incident_repository import IncidentRepository
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident


class InMemoryIncidentRepository(IncidentRepository):
 def __init__(self,items:list[Incident]|None=None): self.items={i.id:i for i in (items or [])}
 def list(self,status:IncidentStatus|None=None,severity:Severity|None=None,store:str|None=None)->list[Incident]:
  return [i for i in self.items.values() if(not status or i.status==status)and(not severity or i.severity==severity)and(not store or i.store==store)]
 def get(self,incident_id:str)->Incident|None:return self.items.get(incident_id)
 def save(self,incident:Incident)->Incident:self.items[incident.id]=incident;return incident
