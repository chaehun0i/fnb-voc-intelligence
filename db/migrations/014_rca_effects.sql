-- 기존 History 외부 효과와 RCA 효과를 분리하며 불확실한 호출은 자동 반복하지 않습니다.
ALTER TABLE serviq_agent_steps DROP CONSTRAINT IF EXISTS serviq_agent_steps_sequence_check;
ALTER TABLE serviq_agent_steps ADD CONSTRAINT serviq_agent_steps_sequence_check CHECK (sequence BETWEEN 1 AND 6);
CREATE TABLE IF NOT EXISTS serviq_rca_effects (
    tenant_id text NOT NULL,
    agent_run_id uuid NOT NULL,
    claimed_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, agent_run_id),
    FOREIGN KEY (tenant_id, agent_run_id) REFERENCES serviq_agent_runs(tenant_id, agent_run_id)
);
DROP TRIGGER IF EXISTS serviq_rca_effects_immutable ON serviq_rca_effects;
CREATE TRIGGER serviq_rca_effects_immutable BEFORE UPDATE OR DELETE ON serviq_rca_effects
FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
