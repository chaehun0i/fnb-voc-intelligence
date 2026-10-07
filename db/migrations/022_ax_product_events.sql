-- Bounded content-free feedback is RAW; never an Approval or Golden truth label.
CREATE TABLE serviq_product_events (
    tenant_id TEXT NOT NULL,
    event_id UUID NOT NULL,
    incident_id TEXT NOT NULL,
    source_run_id UUID,
    event_type TEXT NOT NULL CHECK(event_type IN ('ai_brief_viewed','evidence_opened','explanation_opened',
        'recommendation_accepted','recommendation_edited','recommendation_rejected')),
    occurred_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY(tenant_id,event_id),
    FOREIGN KEY(tenant_id,source_run_id) REFERENCES serviq_agent_runs(tenant_id,agent_run_id)
);
CREATE INDEX serviq_product_incident ON serviq_product_events(tenant_id,incident_id,occurred_at DESC);
CREATE TRIGGER serviq_product_events_no_mutation BEFORE UPDATE OR DELETE ON serviq_product_events
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
