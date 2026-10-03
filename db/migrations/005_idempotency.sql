-- 같은 조직·요청자·명령 범위 안에서 키를 한 번만 처리합니다.
CREATE TABLE IF NOT EXISTS serviq_idempotency (
    tenant_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    key TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'IN_PROGRESS' CHECK (status IN ('IN_PROGRESS','COMPLETED')),
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(tenant_id,principal_id,operation,key)
);
