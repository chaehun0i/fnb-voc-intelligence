-- Incident boolean과 분리된 승인 요청·결정의 정본입니다.
CREATE TABLE IF NOT EXISTS serviq_approvals (
    approval_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    incident_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version>0),
    status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED')),
    requested_at TIMESTAMPTZ NOT NULL,
    document JSONB NOT NULL,
    FOREIGN KEY(tenant_id,incident_id) REFERENCES serviq_incidents(tenant_id,id)
);
CREATE INDEX IF NOT EXISTS serviq_approval_tenant_status
    ON serviq_approvals(tenant_id,status,requested_at);
