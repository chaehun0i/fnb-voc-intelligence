-- 원문 prompt/response 없이 호출별 안전한 사용량만 append-only로 저장합니다.
CREATE TABLE IF NOT EXISTS serviq_llm_calls (
    call_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    incident_id TEXT,
    config_version INTEGER NOT NULL CHECK (config_version >= 0),
    persisted_config_version INTEGER GENERATED ALWAYS AS (NULLIF(config_version,0)) STORED,
    created_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    FOREIGN KEY (tenant_id,incident_id) REFERENCES serviq_incidents(tenant_id,id),
    FOREIGN KEY (tenant_id,persisted_config_version) REFERENCES serviq_config_versions(tenant_id,config_version)
);
CREATE INDEX IF NOT EXISTS serviq_llm_calls_history ON serviq_llm_calls(tenant_id,incident_id,created_at DESC);
DROP TRIGGER IF EXISTS serviq_llm_calls_no_mutation ON serviq_llm_calls;
CREATE TRIGGER serviq_llm_calls_no_mutation BEFORE UPDATE OR DELETE ON serviq_llm_calls
    FOR EACH ROW EXECUTE FUNCTION serviq_decision_immutable();
