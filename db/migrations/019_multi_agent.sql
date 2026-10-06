-- Synthetic read-only operational facts, not a POS/ERP Connector.
CREATE TABLE serviq_operational_observations (
    tenant_id TEXT NOT NULL,
    store TEXT NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('TRANSACTION','INVENTORY')),
    source_ref TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY(tenant_id,store,source_ref)
);
CREATE INDEX serviq_operational_window ON serviq_operational_observations(tenant_id,store,agent_type,observed_at);
CREATE TABLE serviq_investigation_branches (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    agent_type TEXT NOT NULL CHECK(agent_type IN ('HISTORY','TRANSACTION','INVENTORY')),
    document JSONB NOT NULL,
    PRIMARY KEY(tenant_id,agent_run_id,agent_type),
    FOREIGN KEY(tenant_id,agent_run_id) REFERENCES serviq_agent_runs(tenant_id,agent_run_id)
);
CREATE TRIGGER serviq_branches_no_mutation BEFORE UPDATE OR DELETE ON serviq_investigation_branches
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
