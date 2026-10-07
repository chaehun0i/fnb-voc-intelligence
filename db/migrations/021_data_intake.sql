-- Tenant-scoped store registry and bounded data intake records, separate from AI trace.
CREATE TABLE serviq_data_intake (
    tenant_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    store TEXT NOT NULL,
    document JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,kind,resource_id)
);
CREATE INDEX serviq_intake_store ON serviq_data_intake(tenant_id,store,kind);
