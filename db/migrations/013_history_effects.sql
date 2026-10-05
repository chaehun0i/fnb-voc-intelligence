-- 외부 LLM 호출의 불확실한 재전달은 자동 재호출하지 않습니다.
CREATE TABLE IF NOT EXISTS serviq_history_effects (
    tenant_id TEXT NOT NULL,
    agent_run_id UUID NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(tenant_id,agent_run_id),
    FOREIGN KEY(tenant_id,agent_run_id) REFERENCES serviq_agent_runs(tenant_id,agent_run_id)
);
DROP TRIGGER IF EXISTS serviq_history_effects_no_mutation ON serviq_history_effects;
CREATE TRIGGER serviq_history_effects_no_mutation BEFORE UPDATE OR DELETE ON serviq_history_effects
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
