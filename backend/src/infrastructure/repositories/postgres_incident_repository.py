"""버전 확인과 Outbox 기록을 같은 PostgreSQL 트랜잭션으로 저장합니다."""

from dataclasses import replace
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from src.application.ports.incident_repository import IncidentConflict
from src.domain.incidents.enums import IncidentStatus, Severity
from src.domain.incidents.models import Incident
from src.infrastructure.incident_codec import incident_document, incident_from_document


class PostgresIncidentRepository:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def list(self, status: IncidentStatus | None = None, severity: Severity | None = None, store: str | None = None, *, tenant_id: str | None = None) -> list[Incident]:
        with psycopg.connect(self.dsn) as connection:
            rows = connection.execute("""SELECT document FROM serviq_incidents
                WHERE (%s::text IS NULL OR status=%s)
                AND (%s::text IS NULL OR severity=%s)
                AND (%s::text IS NULL OR store=%s)
                AND (%s::text IS NULL OR tenant_id=%s)
                ORDER BY document->>'created_at' DESC, id""", (status, status, severity, severity, store, store, tenant_id, tenant_id)).fetchall()
        return [incident_from_document(row[0]) for row in rows]

    def get(self, incident_id: str, *, tenant_id: str | None = None) -> Incident | None:
        with psycopg.connect(self.dsn) as connection:
            row = connection.execute("SELECT document FROM serviq_incidents WHERE id=%s AND (%s::text IS NULL OR tenant_id=%s)", (incident_id, tenant_id, tenant_id)).fetchone()
        return incident_from_document(row[0]) if row else None

    def save(self, incident: Incident) -> Incident:
        saved = replace(incident, version=incident.version + 1)
        document = incident_document(saved)
        with psycopg.connect(self.dsn) as connection:
            previous = connection.execute("SELECT status FROM serviq_incidents WHERE id=%s AND tenant_id=%s FOR UPDATE", (incident.id, incident.tenant_id)).fetchone()
            if incident.version == 0:
                row = connection.execute("""INSERT INTO serviq_incidents(id,version,status,severity,store,document,tenant_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO NOTHING RETURNING id""", (saved.id, saved.version, saved.status, saved.severity, saved.store, Jsonb(document), saved.tenant_id)).fetchone()
            else:
                row = connection.execute("""UPDATE serviq_incidents SET version=%s,status=%s,severity=%s,store=%s,document=%s,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s AND version=%s AND tenant_id=%s RETURNING id""", (saved.version, saved.status, saved.severity, saved.store, Jsonb(document), saved.id, incident.version, incident.tenant_id)).fetchone()
            if row is None:
                raise IncidentConflict("다른 변경이 먼저 저장되었습니다.")
            if previous is None or previous[0] != str(saved.status):
                event = {"event_id": str(uuid4()), "event_type": "incident.created" if previous is None else "incident.state_changed", "event_version": 1, "aggregate_id": saved.id, "aggregate_version": saved.version, "from_status": previous[0] if previous else None, "to_status": str(saved.status), "occurred_at": saved.timeline[-1].occurred_at if saved.timeline else saved.created_at, "correlation_id": saved.id}
                event["tenant_id"] = saved.tenant_id
                connection.execute("INSERT INTO serviq_outbox(event_id,incident_id,event_type,payload,tenant_id) VALUES(%s,%s,%s,%s,%s)", (event["event_id"], saved.id, event["event_type"], Jsonb(event), saved.tenant_id))
        return incident_from_document(document)
