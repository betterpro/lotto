-- Many-to-many: users can belong to multiple groups.
-- users.group_id = currently active group (rounds, deposits, invites default).

CREATE TABLE IF NOT EXISTS group_members (
    group_id   BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    role       TEXT   NOT NULL DEFAULT 'member',
    joined_at  TEXT   NOT NULL
               DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_user_id ON group_members(user_id);

-- Backfill from users.group_id
INSERT INTO group_members (group_id, user_id, role)
SELECT u.group_id, u.telegram_id,
       CASE WHEN g.trustee_user_id = u.telegram_id THEN 'trustee' ELSE 'member' END
FROM users u
JOIN groups g ON g.id = u.group_id
WHERE u.group_id IS NOT NULL
ON CONFLICT (group_id, user_id) DO NOTHING;

-- Ensure every group trustee is a member
INSERT INTO group_members (group_id, user_id, role)
SELECT g.id, g.trustee_user_id, 'trustee'
FROM groups g
ON CONFLICT (group_id, user_id) DO NOTHING;
