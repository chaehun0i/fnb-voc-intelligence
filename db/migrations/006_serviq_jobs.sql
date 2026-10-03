-- Outbox와 분리된 작업 실행 상태와 재시도 원본을 보존합니다.
CREATE TABLE IF NOT EXISTS serviq_jobs (
    job_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    incident_id TEXT,
    store TEXT,
    correlation_id TEXT NOT NULL,
    dispatch_id TEXT UNIQUE,
    parent_job_id TEXT,
    status TEXT NOT NULL CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','DLQ','CANCELLED')),
    priority TEXT NOT NULL CHECK (priority IN ('P1','P2','P3')),
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0 AND attempt <= max_attempts),
    version INTEGER NOT NULL CHECK (version > 0),
    available_at TIMESTAMPTZ NOT NULL,
    lease_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    document JSONB NOT NULL,
    UNIQUE (tenant_id,job_id),
    FOREIGN KEY (tenant_id,incident_id) REFERENCES serviq_incidents(tenant_id,id),
    FOREIGN KEY (tenant_id,parent_job_id) REFERENCES serviq_jobs(tenant_id,job_id)
);
CREATE INDEX IF NOT EXISTS serviq_jobs_tenant_status ON serviq_jobs(tenant_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS serviq_jobs_claim ON serviq_jobs(status,priority,available_at,created_at);
CREATE INDEX IF NOT EXISTS serviq_jobs_lease ON serviq_jobs(lease_until) WHERE status='RUNNING';
CREATE INDEX IF NOT EXISTS serviq_jobs_correlation ON serviq_jobs(tenant_id,correlation_id);
CREATE INDEX IF NOT EXISTS serviq_jobs_incident ON serviq_jobs(tenant_id,incident_id);
