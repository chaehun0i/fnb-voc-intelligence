"""Append-only tenant-scoped product events, separate from business Audit."""
from psycopg.types.json import Jsonb

from src.ai.ax.models import ProductEvent
from src.ai.ax.validation import ValidationSession
from src.application.security.principal import AccessError


class ProductEventRepository:
    def __init__(self, tenant_id, memory, connection=None):
        self.tenant_id, self.memory, self.connection = tenant_id, memory, connection

    def append(self, event):
        if event.tenant_id != self.tenant_id:
            raise AccessError()
        if self.connection:
            self.connection.execute("INSERT INTO serviq_product_events(tenant_id,event_id,incident_id,source_run_id,event_type,occurred_at,document,session_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                (self.tenant_id, event.event_id, event.incident_id, event.source_run_id, event.event_type,
                 event.occurred_at, Jsonb(event.model_dump(mode="json")), event.session_id))
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

    def get_session(self, identifier, *, lock=False):
        if self.connection:
            row = self.connection.execute("SELECT document,owner_ref FROM serviq_validation_sessions WHERE tenant_id=%s AND session_id=%s" + (" FOR UPDATE" if lock else ""),
                (self.tenant_id, identifier)).fetchone()
        else:
            row = self.memory.data.get("validation_sessions", {}).get((self.tenant_id, str(identifier)))
        return (ValidationSession.model_validate(row[0]), row[1]) if row else None

    def save_session(self, item, owner):
        if item.tenant_id != self.tenant_id:
            raise AccessError()
        document = item.model_dump(mode="json")
        if self.connection:
            self.connection.execute("INSERT INTO serviq_validation_sessions(tenant_id,session_id,owner_ref,store,status,created_at,document) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(tenant_id,session_id) DO UPDATE SET status=EXCLUDED.status,document=EXCLUDED.document WHERE serviq_validation_sessions.owner_ref=EXCLUDED.owner_ref",
                (self.tenant_id, item.session_id, owner, item.store_id, item.status, item.created_at, Jsonb(document)))
        else:
            self.memory.data.setdefault("validation_sessions", {})[(self.tenant_id, str(item.session_id))] = (document, owner)

    def sessions(self, store, limit=101):
        if not 1 <= limit <= 101:
            raise ValueError("VALIDATION_SESSION_LIMIT")
        if self.connection:
            rows = self.connection.execute("SELECT document FROM serviq_validation_sessions WHERE tenant_id=%s AND store=%s ORDER BY created_at DESC,session_id LIMIT %s",
                (self.tenant_id, store, limit)).fetchall()
            return [ValidationSession.model_validate(r[0]) for r in rows]
        items = [ValidationSession.model_validate(r[0]) for (t, _), r in self.memory.data.get("validation_sessions", {}).items()
            if t == self.tenant_id and r[0]["store_id"] == store]
        return sorted(items, key=lambda s: (s.created_at, str(s.session_id)), reverse=True)[:limit]

    def session_events(self, identifier):
        if self.connection:
            return [ProductEvent.model_validate(r[0]) for r in self.connection.execute(
                "SELECT document FROM serviq_product_events WHERE tenant_id=%s AND session_id=%s ORDER BY occurred_at,event_id LIMIT 501",
                (self.tenant_id, identifier)).fetchall()]
        return sorted((e for (t, _), e in self.memory.data.get("product_events", {}).items()
            if t == self.tenant_id and e.session_id == identifier), key=lambda e: (e.occurred_at, e.event_id))[:501]
