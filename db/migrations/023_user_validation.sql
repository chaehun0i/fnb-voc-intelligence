-- User task observation is not Audit, and never stores business/raw AI content.
CREATE TABLE serviq_validation_sessions (
    tenant_id TEXT NOT NULL,
    session_id UUID NOT NULL,
    owner_ref TEXT NOT NULL,
    store TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE','COMPLETED','ABANDONED')),
    created_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL CHECK(octet_length(document::text) <= 4096),
    PRIMARY KEY(tenant_id,session_id)
);
CREATE INDEX serviq_validation_store ON serviq_validation_sessions(tenant_id,store,created_at DESC);
ALTER TABLE serviq_product_events DROP CONSTRAINT serviq_product_events_event_type_check;
ALTER TABLE serviq_product_events ADD CONSTRAINT serviq_product_events_event_type_check
    CHECK(event_type IN ('ai_brief_viewed','evidence_opened','explanation_opened',
        'recommendation_accepted','recommendation_edited','recommendation_rejected','user_validation'));
ALTER TABLE serviq_product_events ADD COLUMN session_id UUID;
ALTER TABLE serviq_product_events ADD CONSTRAINT serviq_product_validation_scope
    FOREIGN KEY(tenant_id,session_id) REFERENCES serviq_validation_sessions(tenant_id,session_id);
CREATE INDEX serviq_product_validation ON serviq_product_events(tenant_id,session_id,occurred_at);
