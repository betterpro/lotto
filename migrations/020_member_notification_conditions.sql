-- Add member activity conditions and attributable group invitations.
-- These tables remain backend-only; no Data API grants are added.

ALTER TABLE group_members
    ADD COLUMN IF NOT EXISTS invited_by_user_id BIGINT
        REFERENCES users(telegram_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_group_members_group_inviter
    ON group_members (group_id, invited_by_user_id)
    WHERE invited_by_user_id IS NOT NULL;

ALTER TABLE notification_rules
    DROP CONSTRAINT IF EXISTS notification_rules_condition_field_check;

ALTER TABLE notification_rules
    ADD CONSTRAINT notification_rules_condition_field_check
    CHECK (condition_field IN (
        'credit', 'current_round_joined', 'current_round_shares', 'successful_invites'
    ));

ALTER TABLE notification_rules
    DROP CONSTRAINT IF EXISTS notification_rules_operator_check;

ALTER TABLE notification_rules
    ADD CONSTRAINT notification_rules_operator_check
    CHECK (operator IN ('lt', 'lte', 'gt', 'gte', 'eq', 'neq'));
