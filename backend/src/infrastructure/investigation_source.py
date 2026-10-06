"""MVP synthetic 운영 자료의 read-only adapter. 실제 POS/ERP Connector가 아닙니다."""
from datetime import timedelta

import psycopg

from src.ai.workflow.agents import SourceUnavailable
from src.ai.workflow.models import OperationalObservation, TenantCapability


class MemoryInvestigationSource:
    def __init__(self, observations=(), *, history_available=False):
        self.items = tuple(OperationalObservation.model_validate(o.model_dump()) for o in observations)
        self.history_available = history_available

    def capabilities(self, tenant_id, store, now):
        result = [TenantCapability(tenant_id=tenant_id, store=store, capability="HISTORY_DATA",
            available=self.history_available, source="AUTHORIZED_HISTORY_SEARCH", freshness="FRESH",
            health="HEALTHY", checked_at=now)]
        for agent in ("TRANSACTION", "INVENTORY"):
            times = [o.observed_at for o in self.items if o.tenant_id == tenant_id and o.store == store and o.agent_type == agent]
            result.append(TenantCapability(tenant_id=tenant_id, store=store, capability=agent+"_DATA",
                available=bool(times), source="FILE_IMPORTED_OBSERVATION" if any(o.source == "FILE_IMPORTED_OBSERVATION"
                    for o in self.items if o.tenant_id == tenant_id and o.store == store and o.agent_type == agent)
                    else "SYNTHETIC_OPERATIONAL_FIXTURE", freshness="FRESH" if times
                    and timedelta(0) <= now-max(times) <= timedelta(hours=24) else "STALE" if times else "UNKNOWN",
                health="HEALTHY", checked_at=now))
        return tuple(result)

    def observations(self, context):
        return tuple(o for o in self.items if o.tenant_id == context.tenant_id and o.store == context.store
            and o.agent_type == context.agent_type and context.window_start <= o.observed_at <= context.window_end)[:20]


class PostgresInvestigationSource:
    def __init__(self, dsn):
        self.dsn = dsn

    def capabilities(self, tenant_id, store, now):
        with psycopg.connect(self.dsn, connect_timeout=5) as connection:
            connection.execute("SET LOCAL statement_timeout='5s'")
            history = connection.execute("SELECT EXISTS(SELECT 1 FROM serviq_history_sources WHERE tenant_id=%s AND store=%s) OR EXISTS(SELECT 1 FROM serviq_data_intake WHERE tenant_id=%s AND store=%s AND kind='SOURCE' AND document->>'kind'='VOC')",
                (tenant_id, store, tenant_id, store)).fetchone()[0]
            rows = connection.execute("SELECT DISTINCT ON (agent_type) document FROM serviq_operational_observations WHERE tenant_id=%s AND store=%s ORDER BY agent_type,observed_at DESC,source_ref",
                (tenant_id, store)).fetchall()
        return MemoryInvestigationSource([OperationalObservation.model_validate(r[0]) for r in rows],
            history_available=history).capabilities(tenant_id, store, now)

    def observations(self, context):
        try:
            with psycopg.connect(self.dsn, connect_timeout=5) as connection:
                connection.execute("SET LOCAL statement_timeout='5s'")
                rows = connection.execute("""SELECT document FROM serviq_operational_observations
                    WHERE tenant_id=%s AND store=%s AND agent_type=%s AND observed_at BETWEEN %s AND %s
                    ORDER BY observed_at DESC,source_ref LIMIT 20""", (context.tenant_id, context.store,
                    context.agent_type, context.window_start, context.window_end)).fetchall()
            return tuple(OperationalObservation.model_validate(r[0]) for r in rows)
        except psycopg.Error:
            raise SourceUnavailable() from None
