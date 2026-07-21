-- Persist the writing direction used by notification rule messages.

ALTER TABLE notification_rules
    ADD COLUMN IF NOT EXISTS text_direction TEXT NOT NULL DEFAULT 'auto';

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'notification_rules_text_direction_check'
          AND conrelid = 'notification_rules'::regclass
    ) THEN
        ALTER TABLE notification_rules
            ADD CONSTRAINT notification_rules_text_direction_check
            CHECK (text_direction IN ('auto', 'ltr', 'rtl'));
    END IF;
END $$;

ALTER TABLE notification_rules ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE notification_rules FROM anon, authenticated;
