-- Bounded operation claims/results and human control are append-only, tenant-scoped.
CREATE TABLE serviq_runtime_events (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    sequence BIGINT NOT NULL CHECK(sequence > 0),
    event_id TEXT NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY(tenant_id,agent_run_id,sequence),
    UNIQUE(tenant_id,agent_run_id,event_id),
    FOREIGN KEY(tenant_id,agent_run_id) REFERENCES serviq_agent_runs(tenant_id,agent_run_id),
    CHECK(document->>'kind' IN ('CLAIM','RESULT','CONTROL','HARNESS'))
);
CREATE TRIGGER serviq_runtime_events_no_mutation BEFORE UPDATE OR DELETE ON serviq_runtime_events
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
CREATE FUNCTION serviq_manifest_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.document->'manifest' IS DISTINCT FROM NEW.document->'manifest' THEN
        RAISE EXCEPTION 'MANIFEST_IMMUTABLE';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER serviq_manifest_no_change BEFORE UPDATE ON serviq_agent_runs
    FOR EACH ROW EXECUTE FUNCTION serviq_manifest_immutable();
