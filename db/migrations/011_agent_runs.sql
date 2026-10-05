-- 운영 이력과 LangGraph 복구 테이블은 분리합니다.
CREATE UNIQUE INDEX IF NOT EXISTS serviq_decision_run_lineage ON serviq_decisions(tenant_id,decision_id,incident_id,config_version);
CREATE TABLE IF NOT EXISTS serviq_agent_runs (
    agent_run_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    workflow_id UUID NOT NULL UNIQUE,
    config_version INTEGER NOT NULL,
    jev_decision_id UUID NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    UNIQUE(tenant_id,job_id),
    UNIQUE(tenant_id,agent_run_id),
    FOREIGN KEY(tenant_id,incident_id) REFERENCES serviq_incidents(tenant_id,id),
    FOREIGN KEY(tenant_id,job_id) REFERENCES serviq_jobs(tenant_id,job_id),
    FOREIGN KEY(tenant_id,config_version) REFERENCES serviq_config_versions(tenant_id,config_version),
    FOREIGN KEY(tenant_id,jev_decision_id,incident_id,config_version)
        REFERENCES serviq_decisions(tenant_id,decision_id,incident_id,config_version)
);
CREATE INDEX IF NOT EXISTS serviq_agent_runs_history ON serviq_agent_runs(tenant_id,incident_id,started_at DESC);
CREATE TABLE IF NOT EXISTS serviq_agent_steps (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    sequence INTEGER NOT NULL CHECK(sequence BETWEEN 1 AND 3),
    attempt INTEGER NOT NULL CHECK(attempt>0),
    document JSONB NOT NULL,
    PRIMARY KEY(tenant_id,agent_run_id,sequence,attempt),
    FOREIGN KEY(tenant_id,agent_run_id) REFERENCES serviq_agent_runs(tenant_id,agent_run_id)
);
DROP TRIGGER IF EXISTS serviq_agent_steps_no_mutation ON serviq_agent_steps;
CREATE TRIGGER serviq_agent_steps_no_mutation BEFORE UPDATE OR DELETE ON serviq_agent_steps
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
