-- Day 16 자료는 명시적인 로컬 개발 조직으로 보존합니다.
ALTER TABLE serviq_incidents ADD COLUMN IF NOT EXISTS
    tenant_id TEXT NOT NULL DEFAULT 'legacy-local';
UPDATE serviq_incidents SET document = document || jsonb_build_object('tenant_id', tenant_id)
    WHERE NOT document ? 'tenant_id';
CREATE UNIQUE INDEX IF NOT EXISTS serviq_incident_tenant_id
    ON serviq_incidents(tenant_id, id);
CREATE INDEX IF NOT EXISTS serviq_incident_tenant_filter
    ON serviq_incidents(tenant_id, status, severity, store);
ALTER TABLE serviq_outbox ADD COLUMN IF NOT EXISTS
    tenant_id TEXT NOT NULL DEFAULT 'legacy-local';
UPDATE serviq_outbox o SET tenant_id=i.tenant_id
    FROM serviq_incidents i WHERE o.incident_id=i.id AND o.tenant_id<>i.tenant_id;
CREATE INDEX IF NOT EXISTS serviq_outbox_tenant ON serviq_outbox(tenant_id, status);
