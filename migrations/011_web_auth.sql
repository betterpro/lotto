-- Web authentication: email + password and Google (Apple later).
--
-- The users table stays keyed on telegram_id. Web-only accounts get a synthetic
-- NEGATIVE id from web_user_id_seq, which can never collide with a real Telegram
-- id (those are always positive). When such a user later signs in with Telegram,
-- the two accounts are merged (see merge_users in database.py).

ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_email     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash  TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub     TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS apple_sub      TEXT;
-- How the account was originally created: 'telegram' | 'email' | 'google' | 'apple'
ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider  TEXT;

-- Login identity uniqueness (case-insensitive email; one account per OAuth sub).
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_auth_email
    ON users (lower(auth_email)) WHERE auth_email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub
    ON users (google_sub) WHERE google_sub IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_apple_sub
    ON users (apple_sub) WHERE apple_sub IS NOT NULL;

-- Synthetic id allocator for web-only accounts (used as -nextval).
CREATE SEQUENCE IF NOT EXISTS web_user_id_seq START 1;
