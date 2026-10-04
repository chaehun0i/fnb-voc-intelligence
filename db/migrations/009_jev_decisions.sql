-- Jev의 Shadow 판단은 조직·Incident·Job·Config 원본 참조를 보존합니다.
CREATE TABLE IF NOT EXISTS serviq_decisions (
    decision_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    source_job_id TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    config_version INTEGER NOT NULL CHECK (config_version >= 0),
    persisted_config_version INTEGER GENERATED ALWAYS AS (NULLIF(config_version,0)) STORED,
    mode TEXT NOT NULL CHECK (mode='SHADOW'),
    input_digest TEXT NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),
    decided_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    UNIQUE (tenant_id, source_job_id, ruleset_version),
    FOREIGN KEY (tenant_id,incident_id) REFERENCES serviq_incidents(tenant_id,id),
    FOREIGN KEY (tenant_id,source_job_id) REFERENCES serviq_jobs(tenant_id,job_id),
    FOREIGN KEY (tenant_id,persisted_config_version) REFERENCES serviq_config_versions(tenant_id,config_version)
);
CREATE INDEX IF NOT EXISTS serviq_decision_history ON serviq_decisions(tenant_id,incident_id,decided_at DESC,decision_id);
CREATE OR REPLACE FUNCTION serviq_decision_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'decision audit is append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS serviq_decision_no_mutation ON serviq_decisions;
CREATE TRIGGER serviq_decision_no_mutation BEFORE UPDATE OR DELETE ON serviq_decisions
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
