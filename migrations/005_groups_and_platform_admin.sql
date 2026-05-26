-- Multi-trustee groups and platform admin
-- Run in Supabase SQL Editor after 003 and 004.

CREATE TABLE IF NOT EXISTS groups (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT    NOT NULL,
    slug             TEXT    NOT NULL UNIQUE,
    trustee_user_id  BIGINT  NOT NULL REFERENCES users(telegram_id),
    status           TEXT    NOT NULL DEFAULT 'active',
    etransfer_email  TEXT,
    created_at       TEXT    NOT NULL
                     DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS trustee_applications (
    id                  BIGSERIAL PRIMARY KEY,
    applicant_user_id   BIGINT  NOT NULL REFERENCES users(telegram_id),
    proposed_group_name TEXT    NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'pending',
    reviewed_by         BIGINT  REFERENCES users(telegram_id),
    review_notes        TEXT,
    created_at          TEXT    NOT NULL
                        DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    reviewed_at         TEXT
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS group_id BIGINT REFERENCES groups(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_platform_admin INTEGER NOT NULL DEFAULT 0;

ALTER TABLE rounds ADD COLUMN IF NOT EXISTS group_id BIGINT REFERENCES groups(id);
ALTER TABLE deposit_requests ADD COLUMN IF NOT EXISTS group_id BIGINT REFERENCES groups(id);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS group_id BIGINT REFERENCES groups(id);

-- Default group for existing deployment (trustee from first user with is_trustee=1, else first user)
INSERT INTO groups (name, slug, trustee_user_id, status)
SELECT
    'Lotto Chee',
    'lotto-chee',
    COALESCE(
        (SELECT telegram_id FROM users WHERE is_trustee = 1 ORDER BY telegram_id LIMIT 1),
        (SELECT telegram_id FROM users ORDER BY telegram_id LIMIT 1)
    ),
    'active'
WHERE NOT EXISTS (SELECT 1 FROM groups WHERE slug = 'lotto-chee');

UPDATE users SET group_id = (SELECT id FROM groups WHERE slug = 'lotto-chee' LIMIT 1)
WHERE group_id IS NULL;

UPDATE rounds SET group_id = (SELECT id FROM groups WHERE slug = 'lotto-chee' LIMIT 1)
WHERE group_id IS NULL;

UPDATE deposit_requests dr SET group_id = u.group_id
FROM users u WHERE dr.user_id = u.telegram_id AND dr.group_id IS NULL;

UPDATE transactions t SET group_id = u.group_id
FROM users u WHERE t.user_id = u.telegram_id AND t.group_id IS NULL;

-- Platform admins: set is_platform_admin=1 for legacy global trustee (optional one-time backfill)
UPDATE users SET is_platform_admin = 1 WHERE is_trustee = 1;
-- After deploy, set PLATFORM_ADMIN_TELEGRAM_IDS in env; new users get is_platform_admin from that list.
