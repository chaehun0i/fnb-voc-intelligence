from .schemas.incidents import IncidentResponse


def incident_response(i): return IncidentResponse(id=i.id,display_id=i.display_id,title=i.title,severity=i.severity,status=i.status,store=i.store,owner=i.owner,created_at=i.created_at,sla_due_at=i.sla_due_at)
