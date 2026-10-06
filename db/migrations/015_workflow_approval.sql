-- 기존 Approval과 AgentRun의 조직별 lineage만 추가합니다. 새로운 승인 subsystem이 아닙니다.
ALTER TABLE serviq_approvals ADD COLUMN IF NOT EXISTS agent_run_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS uq_workflow_approval
    ON serviq_approvals(tenant_id, agent_run_id) WHERE agent_run_id IS NOT NULL;
ALTER TABLE serviq_approvals DROP CONSTRAINT IF EXISTS fk_workflow_approval_run;
ALTER TABLE serviq_approvals ADD CONSTRAINT fk_workflow_approval_run
    FOREIGN KEY (tenant_id, agent_run_id) REFERENCES serviq_agent_runs(tenant_id, agent_run_id);
