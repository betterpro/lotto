-- General WHEN/THEN notification models for group-authored event automations.

ALTER TABLE notification_rules
    ADD COLUMN IF NOT EXISTS trigger_type TEXT NOT NULL DEFAULT 'condition',
    ADD COLUMN IF NOT EXISTS event_key TEXT;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'notification_rules_trigger_type_check'
          AND conrelid = 'notification_rules'::regclass
    ) THEN
        ALTER TABLE notification_rules
            ADD CONSTRAINT notification_rules_trigger_type_check
            CHECK (trigger_type IN ('condition', 'event'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'notification_rules_event_key_check'
          AND conrelid = 'notification_rules'::regclass
    ) THEN
        ALTER TABLE notification_rules
            ADD CONSTRAINT notification_rules_event_key_check
            CHECK (trigger_type = 'condition' OR event_key IS NOT NULL);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_notification_rules_group_event
    ON notification_rules (group_id, event_key)
    WHERE enabled = 1 AND trigger_type = 'event';

ALTER TABLE notification_deliveries
    ADD COLUMN IF NOT EXISTS event_key TEXT,
    ADD COLUMN IF NOT EXISTS delivery_key TEXT;

ALTER TABLE notification_deliveries
    DROP CONSTRAINT IF EXISTS notification_deliveries_rule_id_user_id_match_cycle_key;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_deliveries_condition_unique
    ON notification_deliveries (rule_id, user_id, match_cycle)
    WHERE delivery_key IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_deliveries_event_unique
    ON notification_deliveries (rule_id, user_id, delivery_key)
    WHERE delivery_key IS NOT NULL;

ALTER TABLE notification_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_rule_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_deliveries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE notification_rules FROM anon, authenticated;
REVOKE ALL ON TABLE notification_rule_states FROM anon, authenticated;
REVOKE ALL ON TABLE notification_deliveries FROM anon, authenticated;
