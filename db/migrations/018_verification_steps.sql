ALTER TABLE serviq_agent_steps DROP CONSTRAINT serviq_agent_steps_sequence_check;
ALTER TABLE serviq_agent_steps ADD CONSTRAINT serviq_agent_steps_sequence_check CHECK (sequence BETWEEN 1 AND 15);
CREATE TABLE IF NOT EXISTS serviq_internal_review_simulations (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    document JSONB NOT NULL,
    PRIMARY KEY (tenant_id, agent_run_id),
    FOREIGN KEY (tenant_id, agent_run_id) REFERENCES serviq_agent_runs(tenant_id, agent_run_id)
);
