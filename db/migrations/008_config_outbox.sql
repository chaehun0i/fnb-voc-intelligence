-- Incident FK를 보존하면서 독립 Config 리소스의 이벤트를 허용합니다.
ALTER TABLE serviq_outbox ALTER COLUMN incident_id DROP NOT NULL;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='serviq_outbox'::regclass
                   AND conname='serviq_outbox_resource') THEN
        ALTER TABLE serviq_outbox ADD CONSTRAINT serviq_outbox_resource CHECK (
            (event_type='config.changed' AND incident_id IS NULL
             AND payload->>'resource_type'='runtime_config') OR
            (event_type<>'config.changed' AND incident_id IS NOT NULL));
    END IF;
END;
$$;
