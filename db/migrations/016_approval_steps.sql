ALTER TABLE serviq_agent_steps DROP CONSTRAINT IF EXISTS serviq_agent_steps_sequence_check;
ALTER TABLE serviq_agent_steps ADD CONSTRAINT serviq_agent_steps_sequence_check
    CHECK (sequence BETWEEN 1 AND 11);
