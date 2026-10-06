-- 외부 write가 아닌 immutable 내부 실행 기록 및 조치 후 normalized source.
CREATE TABLE IF NOT EXISTS serviq_internal_executions (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    execution_id UUID NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY (tenant_id, execution_id),
    UNIQUE (tenant_id, agent_run_id),
    FOREIGN KEY (tenant_id, agent_run_id) REFERENCES serviq_agent_runs(tenant_id, agent_run_id)
);
CREATE TABLE IF NOT EXISTS serviq_verification_evidence (
    tenant_id TEXT NOT NULL,
    execution_id UUID NOT NULL,
    evidence_id UUID NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY (tenant_id, evidence_id),
    FOREIGN KEY (tenant_id, execution_id) REFERENCES serviq_internal_executions(tenant_id, execution_id)
);
