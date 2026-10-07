"""Read-only business queries over existing Application and source ports."""
from src.ai.execution.tools import ToolInput, ToolItem, ToolResult
from src.application.incidents.service import IncidentNotFound, IncidentService
from src.application.security.principal import AccessError


class BusinessToolQueries:
    def __init__(self, persistence, source):
        self.persistence, self.source = persistence, source

    def read(self, name, arguments, *, principal, context):
        arguments = ToolInput.model_validate(arguments.model_dump())
        if context.tenant_id != principal.tenant_id:
            raise AccessError()
        with self.persistence.transaction(principal.tenant_id) as uow:
            service = IncidentService(uow.incidents, principal=principal)
            incident = service.get(arguments.incident_id)
            if incident.id != context.incident_id or incident.store != context.store:
                raise AccessError()
            if name == "get_incident":
                items = (ToolItem(source_ref="incident:"+incident.id, source_type="INCIDENT",
                    source_at=incident.created_at, provenance=("incident_application",)),)
            elif name == "search_similar_incidents":
                related = sorted((item for item in service.list(store=incident.store)
                    if item.id != incident.id and item.severity == incident.severity), key=lambda i: i.id)
                items = tuple(ToolItem(source_ref="incident:"+item.id, source_type="INCIDENT",
                    source_at=item.created_at, provenance=("incident_application",), rank=rank)
                    for rank, item in enumerate(related[:arguments.limit], 1))
            elif name in {"get_transactions", "get_inventory"}:
                agent = "TRANSACTION" if name == "get_transactions" else "INVENTORY"
                if context.agent_type != agent:
                    raise AccessError()
                observations = self.source.observations(context)
                if any(o.tenant_id != principal.tenant_id or o.store != incident.store
                        or o.agent_type != agent or not context.window_start <= o.observed_at <= context.window_end
                        for o in observations):
                    raise AccessError()
                items = tuple(ToolItem(source_ref=o.source_ref, source_type=agent,
                    observation_code=o.signal, stance=o.stance, source_at=o.observed_at.isoformat(),
                    provenance=("file_imported_operational" if o.source == "FILE_IMPORTED_OBSERVATION"
                        else "synthetic_operational",), rank=rank)
                    for rank, o in enumerate(observations[:arguments.limit], 1))
            else:
                raise IncidentNotFound()
        return ToolResult(tool_name=name, items=items)
