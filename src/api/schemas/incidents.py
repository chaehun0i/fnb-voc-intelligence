from pydantic import BaseModel
class TriageRequest(BaseModel): severity:str|None=None; occurred_at:str="2026-10-02T00:00:00Z"
class IncidentResponse(BaseModel):
 id:str; display_id:str; title:str; severity:str; status:str; store:str; owner:str; created_at:str; sla_due_at:str
