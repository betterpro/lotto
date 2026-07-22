-- One notification preference per member/group replaces category switches.
-- All reads and writes go through the trusted app server.

ALTER TABLE group_members
    ADD COLUMN IF NOT EXISTS notifications_enabled INTEGER NOT NULL DEFAULT 1
    CHECK (notifications_enabled IN (0, 1));

-- Preserve a clear legacy opt-out: members who disabled every old category
-- remain opted out in every group. Mixed category settings migrate to enabled.
UPDATE group_members gm
SET notifications_enabled = 0
FROM user_settings s
WHERE s.user_id = gm.user_id
  AND COALESCE(s.notif_new_round, 1) = 0
  AND COALESCE(s.notif_reminder, 1) = 0
  AND COALESCE(s.notif_ticket, 1) = 0
  AND COALESCE(s.notif_results, 1) = 0
  AND COALESCE(s.notif_contribution, 1) = 0
  AND COALESCE(s.notif_round_closed, 1) = 0;

CREATE INDEX IF NOT EXISTS idx_group_members_notifications
    ON group_members (user_id, group_id, notifications_enabled);
