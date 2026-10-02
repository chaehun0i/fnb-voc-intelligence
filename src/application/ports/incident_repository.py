from typing import Protocol

from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident


class IncidentRepository(Protocol):
 def list(self,status:IncidentStatus|None=None,severity:Severity|None=None,store:str|None=None)->list[Incident]: ...
 def get(self,incident_id:str)->Incident|None: ...
 def save(self,incident:Incident)->Incident: ...
