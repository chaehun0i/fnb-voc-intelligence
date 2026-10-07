"""Append-only tenant-scoped product events, separate from business Audit."""
from psycopg.types.json import Jsonb

from src.ai.ax.models import ProductEvent
from src.application.security.principal import AccessError


class ProductEventRepository:
    def __init__(self, tenant_id, memory, connection=None):
        self.tenant_id, self.memory, self.connection = tenant_id, memory, connection

    def append(self, event):
        if event.tenant_id != self.tenant_id:
            raise AccessError()
        if self.connection:
            self.connection.execute("INSERT INTO serviq_product_events(tenant_id,event_id,incident_id,source_run_id,event_type,occurred_at,document) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (self.tenant_id, event.event_id, event.incident_id, event.source_run_id, event.event_type,
                 event.occurred_at, Jsonb(event.model_dump(mode="json"))))
        else:
            key = (self.tenant_id, event.event_id)
            records = self.memory.data.setdefault("product_events", {})
            if key in records:
                raise AccessError("PRODUCT_EVENT_CONFLICT", 409)
            records[key] = event

    def history(self, incident_id, limit=100):
        if not 1 <= limit <= 100:
            raise ValueError("PRODUCT_EVENT_LIMIT")
        if self.connection:
            return [ProductEvent.model_validate(r[0]) for r in self.connection.execute(
                "SELECT document FROM serviq_product_events WHERE tenant_id=%s AND incident_id=%s ORDER BY occurred_at DESC,event_id LIMIT %s",
                (self.tenant_id, incident_id, limit)).fetchall()]
        return sorted((e for (t, _), e in self.memory.data.get("product_events", {}).items()
            if t == self.tenant_id and e.incident_id == incident_id), key=lambda e: (e.occurred_at, e.event_id), reverse=True)[:limit]
