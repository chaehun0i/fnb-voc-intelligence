-- 설정 이력은 덮어쓰지 않으며 조직 안에서 증가하는 버전을 사용합니다.
CREATE TABLE IF NOT EXISTS serviq_config_versions (
    tenant_id TEXT NOT NULL,
    config_version INTEGER NOT NULL CHECK (config_version > 0),
    scope TEXT NOT NULL DEFAULT 'TENANT' CHECK (scope = 'TENANT'),
    config_json JSONB NOT NULL,
    reason TEXT NOT NULL CHECK (length(btrim(reason)) BETWEEN 1 AND 1000),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    parent_version INTEGER,
    rollback_source INTEGER,
    PRIMARY KEY (tenant_id, config_version),
    FOREIGN KEY (tenant_id, parent_version) REFERENCES serviq_config_versions(tenant_id, config_version),
    FOREIGN KEY (tenant_id, rollback_source) REFERENCES serviq_config_versions(tenant_id, config_version),
    CHECK ((config_version=1 AND parent_version IS NULL) OR
           (config_version>1 AND parent_version IS NOT NULL AND parent_version=config_version-1))
);
CREATE INDEX IF NOT EXISTS serviq_config_current
    ON serviq_config_versions(tenant_id, scope, config_version DESC);
CREATE OR REPLACE FUNCTION serviq_config_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'config versions are append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS serviq_config_no_mutation ON serviq_config_versions;
CREATE TRIGGER serviq_config_no_mutation BEFORE UPDATE OR DELETE ON serviq_config_versions
    FOR EACH ROW EXECUTE FUNCTION serviq_config_immutable();
