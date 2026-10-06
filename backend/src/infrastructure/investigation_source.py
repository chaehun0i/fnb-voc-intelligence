"""MVP synthetic 운영 자료의 read-only adapter. 실제 POS/ERP Connector가 아닙니다."""
from src.ai.workflow.models import OperationalObservation, TenantCapability


class MemoryInvestigationSource:
    def __init__(self, observations=()):
        self.items = tuple(OperationalObservation.model_validate(o.model_dump()) for o in observations)

    def capabilities(self, tenant_id, store, now):
        return tuple(TenantCapability(tenant_id=tenant_id, store=store, capability=agent+"_DATA",
            available=any(o.tenant_id == tenant_id and o.store == store and o.agent_type == agent for o in self.items),
            source="SYNTHETIC_OPERATIONAL_FIXTURE", freshness="FRESH", health="HEALTHY", checked_at=now)
            for agent in ("TRANSACTION", "INVENTORY"))

    def observations(self, context):
        return tuple(o for o in self.items if o.tenant_id == context.tenant_id and o.store == context.store
            and o.agent_type == context.agent_type and context.window_start <= o.observed_at <= context.window_end)[:20]
