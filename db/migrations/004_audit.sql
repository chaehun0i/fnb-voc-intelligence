-- 승인 결정과 독립적인 추기 전용 실행 이력입니다.
CREATE TABLE IF NOT EXISTS serviq_audit (
    audit_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS serviq_audit_tenant_time ON serviq_audit(tenant_id, occurred_at);
CREATE OR REPLACE FUNCTION serviq_audit_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit records are append-only';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS serviq_audit_no_mutation ON serviq_audit;
CREATE TRIGGER serviq_audit_no_mutation BEFORE UPDATE OR DELETE ON serviq_audit
    FOR EACH ROW EXECUTE FUNCTION serviq_audit_immutable();
