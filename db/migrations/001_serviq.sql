-- 기존 Product/Review 테이블과 분리된 ServIQ 저장소를 초기화합니다.
CREATE TABLE IF NOT EXISTS serviq_incidents (
    id TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version > 0),
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    store TEXT NOT NULL,
    document JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS serviq_incident_filter
    ON serviq_incidents(status, severity, store);

CREATE TABLE IF NOT EXISTS serviq_outbox (
    event_id UUID PRIMARY KEY,
    incident_id TEXT NOT NULL REFERENCES serviq_incidents(id),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'DLQ')),
    attempts INTEGER NOT NULL DEFAULT 0
        CONSTRAINT serviq_outbox_attempts_nonnegative CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3
        CONSTRAINT serviq_outbox_max_attempts_positive CHECK (max_attempts > 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_until TIMESTAMPTZ,
    error_summary TEXT,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS serviq_outbox_ready
    ON serviq_outbox(status, available_at);

-- 이전 개발 DB에도 재시도 입력 제약을 추가하며 반복 실행 시 중복하지 않습니다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'serviq_outbox'::regclass
            AND conname = 'serviq_outbox_attempts_nonnegative'
    ) THEN
        ALTER TABLE serviq_outbox ADD CONSTRAINT
            serviq_outbox_attempts_nonnegative CHECK (attempts >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'serviq_outbox'::regclass
            AND conname = 'serviq_outbox_max_attempts_positive'
    ) THEN
        ALTER TABLE serviq_outbox ADD CONSTRAINT
            serviq_outbox_max_attempts_positive CHECK (max_attempts > 0);
    END IF;
END;
$$;
