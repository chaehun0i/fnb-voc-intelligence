"""원본을 복제하지 않고 읽기 전용 snapshot에서 운영 현황을 집계합니다."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import psycopg

from src.application.dashboard.models import (
    CapaCount,
    CauseCount,
    DashboardKpis,
    DashboardSnapshot,
    DashboardUnavailable,
    PriorityIncident,
    TrendBucket,
)
from src.application.dashboard.queries import store_scope


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("원본 시각에는 시간대가 필요합니다.")
    return parsed.astimezone(UTC)


def days(start):
    return [(start + timedelta(days=n)).date().isoformat() for n in range(7)]


class MemoryDashboardProjection:
    """명시적 memory 모드용이며 HTTP DB 실패 fallback이 아닙니다."""

    def __init__(self, persistence):
        self.persistence = persistence

    def project(self, principal, as_of, start):
        repo, state = self.persistence.incidents, self.persistence.memory
        with repo._lock, state.lock:
            scope = store_scope(principal)
            incidents = [item for item in repo.list(tenant_id=principal.tenant_id)
                         if (scope is None or item.store in scope) and timestamp(item.created_at) <= as_of]
            snapshot = self.incidents(incidents, as_of, start)
            ids = {item.id for item in incidents}
            approvals = [item for item in state.data.get("approvals", {}).values()
                         if item.tenant_id == principal.tenant_id and item.incident_id in ids
                         and timestamp(item.requested_at) <= as_of]
            jobs = [item for item in state.data.get("jobs", {}).values()
                    if item.tenant_id == principal.tenant_id and (scope is None or item.store in scope)
                    and item.created_at <= as_of]
            snapshot = replace(snapshot, kpis=replace(snapshot.kpis,
                pending_approvals=sum(a.status == "PENDING" for a in approvals),
                failed_jobs=sum(j.status == "FAILED" for j in jobs),
                dlq_jobs=sum(j.status == "DLQ" for j in jobs),
                queue_depth=sum(j.status == "PENDING" for j in jobs),
                running_jobs=sum(j.status == "RUNNING" for j in jobs)))
            causes = sum(len(item.root_cause_candidates) for item in incidents)
            priorities = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
            opened = sorted([i for i in incidents if i.status not in {"RESOLVED", "CLOSED"}],
                            key=lambda i: (priorities[i.severity], -timestamp(i.created_at).timestamp(), i.id))[:4]
            return replace(snapshot, priority_incidents=[PriorityIncident(i.id, i.title, i.store, i.owner, i.severity) for i in opened],
                root_cause_distribution=[CauseCount("미분류", causes)] if causes else [],
                capa_status=[CapaCount(status, sum(action.status == status for item in incidents for action in item.corrective_actions))
                             for status in ["PROPOSED", "APPROVED", "EXECUTED"]])

    def incidents(self, incidents, as_of, start):
        trend = {day: [0, 0] for day in days(start)}
        for item in incidents:
            created = timestamp(item.created_at)
            if start <= created <= as_of:
                trend[created.date().isoformat()][0] += 1
            resolved = [timestamp(t.occurred_at) for t in item.timeline
                        if t.status == "RESOLVED" and timestamp(t.occurred_at) <= as_of]
            if resolved and start <= max(resolved):
                trend[max(resolved).date().isoformat()][1] += 1
        opened = [item for item in incidents if item.status not in {"RESOLVED", "CLOSED"}]
        return DashboardSnapshot(as_of.isoformat(), [TrendBucket(day, *counts) for day, counts in trend.items()],
            DashboardKpis(open_incidents=len(opened), critical_incidents=sum(i.severity == "CRITICAL" for i in opened)))


class PostgresDashboardProjection:
    def __init__(self, dsn):
        self.dsn = dsn

    def project(self, principal, as_of, start):
        scope = store_scope(principal)
        try:
            with psycopg.connect(self.dsn) as connection:
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                connection.execute("SET LOCAL statement_timeout='5s'")
                snapshot = self.incidents(connection, principal.tenant_id, scope, as_of, start)
                snapshot = self.operations(connection, principal.tenant_id, scope, as_of, snapshot)
                return self.analysis(connection, principal.tenant_id, scope, as_of, snapshot)
        except (psycopg.Error, ValueError, TypeError) as exc:
            raise DashboardUnavailable() from exc

    def incidents(self, connection, tenant, scope, as_of, start):
        predicates = "tenant_id=%s AND (%s::text[] IS NULL OR store=ANY(%s)) AND (document->>'created_at')::timestamptz<=%s"
        params = (tenant, scope, scope, as_of)
        opened, critical = connection.execute(f"""SELECT
            count(*) FILTER(WHERE status NOT IN ('RESOLVED','CLOSED')),
            count(*) FILTER(WHERE status NOT IN ('RESOLVED','CLOSED') AND severity='CRITICAL')
            FROM serviq_incidents WHERE {predicates}""", params).fetchone()
        rows = connection.execute(f"""WITH scoped AS (
            SELECT document FROM serviq_incidents WHERE {predicates}
        ), detected AS (
            SELECT ((document->>'created_at')::timestamptz AT TIME ZONE 'UTC')::date AS bucket_date, count(*) AS n
            FROM scoped WHERE (document->>'created_at')::timestamptz>=%s GROUP BY 1
        ), resolved_times AS (
            SELECT (SELECT max((t->>'occurred_at')::timestamptz)
                FROM jsonb_array_elements(COALESCE(document->'timeline','[]'::jsonb)) t
                WHERE t->>'status'='RESOLVED' AND (t->>'occurred_at')::timestamptz<=%s) AS resolved_at FROM scoped
        ), resolved AS (
            SELECT (resolved_at AT TIME ZONE 'UTC')::date AS bucket_date,count(*) AS n FROM resolved_times WHERE resolved_at>=%s GROUP BY 1
        ) SELECT to_char(d.bucket_date,'YYYY-MM-DD'), COALESCE(a.n,0),COALESCE(r.n,0)
        FROM generate_series(%s::timestamp,%s::timestamp,interval '1 day') d(bucket_date)
        LEFT JOIN detected a ON a.bucket_date=d.bucket_date::date LEFT JOIN resolved r ON r.bucket_date=d.bucket_date::date ORDER BY d.bucket_date""",
            (*params, start, as_of, start, start.replace(tzinfo=None), as_of.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None))).fetchall()
        return DashboardSnapshot(as_of.isoformat(), [TrendBucket(*row) for row in rows],
                                 DashboardKpis(open_incidents=opened, critical_incidents=critical))

    def operations(self, connection, tenant, scope, as_of, snapshot):
        pending = connection.execute("""SELECT count(*) FROM serviq_approvals a
            JOIN serviq_incidents i ON i.tenant_id=a.tenant_id AND i.id=a.incident_id
            WHERE a.tenant_id=%s AND (%s::text[] IS NULL OR i.store=ANY(%s))
            AND a.status='PENDING' AND a.requested_at<=%s
            AND (i.document->>'created_at')::timestamptz<=%s""", (tenant, scope, scope, as_of, as_of)).fetchone()[0]
        failed, dlq, queued, running = connection.execute("""SELECT
            count(*) FILTER(WHERE status='FAILED'),count(*) FILTER(WHERE status='DLQ'),
            count(*) FILTER(WHERE status='PENDING'),count(*) FILTER(WHERE status='RUNNING')
            FROM serviq_jobs WHERE tenant_id=%s AND (%s::text[] IS NULL OR store=ANY(%s))
            AND created_at<=%s""", (tenant, scope, scope, as_of)).fetchone()
        return replace(snapshot, kpis=replace(snapshot.kpis, pending_approvals=pending,
            failed_jobs=failed, dlq_jobs=dlq, queue_depth=queued, running_jobs=running))

    def analysis(self, connection, tenant, scope, as_of, snapshot):
        predicates = "tenant_id=%s AND (%s::text[] IS NULL OR store=ANY(%s)) AND (document->>'created_at')::timestamptz<=%s"
        params = (tenant, scope, scope, as_of)
        causes = connection.execute(f"""SELECT COALESCE(sum(jsonb_array_length(
            COALESCE(document->'root_cause_candidates','[]'::jsonb))),0)
            FROM serviq_incidents WHERE {predicates}""", params).fetchone()[0]
        rows = connection.execute(f"""SELECT action->>'status',count(*)
            FROM (SELECT document FROM serviq_incidents WHERE {predicates}) scoped
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(document->'corrective_actions','[]'::jsonb)) action
            GROUP BY 1""", params).fetchall()
        counts = dict(rows)
        priorities = connection.execute(f"""SELECT id,document->>'title',store,document->>'owner',severity
            FROM serviq_incidents WHERE {predicates} AND status NOT IN ('RESOLVED','CLOSED')
            ORDER BY CASE severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
            (document->>'created_at')::timestamptz DESC,id LIMIT 4""", params).fetchall()
        return replace(snapshot, priority_incidents=[PriorityIncident(*row) for row in priorities],
                       root_cause_distribution=[CauseCount("미분류", causes)] if causes else [],
                       capa_status=[CapaCount(status, counts.get(status, 0)) for status in ["PROPOSED", "APPROVED", "EXECUTED"]])
