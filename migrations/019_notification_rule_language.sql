-- Persist the language used to author each notification rule.

ALTER TABLE notification_rules
    ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'notification_rules_language_check'
          AND conrelid = 'notification_rules'::regclass
    ) THEN
        ALTER TABLE notification_rules
            ADD CONSTRAINT notification_rules_language_check
            CHECK (language IN ('en', 'fa', 'fr'));
    END IF;
END $$;

ALTER TABLE notification_rules ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE notification_rules FROM anon, authenticated;
