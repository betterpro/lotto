-- 010_round_notifications.sql
-- Notification preferences for pool activity and round-closed (trustee) alerts,
-- plus per-round dedup flags so 48h/24h pre-close reminders fire at most once.
-- Idempotent; also auto-applied at startup via database._SCHEMA_STATEMENTS.

ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS notif_contribution INTEGER NOT NULL DEFAULT 1;
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS notif_round_closed INTEGER NOT NULL DEFAULT 1;

ALTER TABLE rounds ADD COLUMN IF NOT EXISTS reminder_48h_sent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS reminder_24h_sent INTEGER NOT NULL DEFAULT 0;
