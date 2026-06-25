-- Group join codes.
--
-- Each group gets a short, human-friendly code (e.g. "K7P2QM"). The trustee
-- shares it however they like (chat, in person); a new member types it on the
-- "join a group" screen to become a member. Codes are allocated lazily on first
-- use (see ensure_join_code in group_context.py) and for new groups at creation.

ALTER TABLE groups ADD COLUMN IF NOT EXISTS join_code TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_groups_join_code
    ON groups (join_code) WHERE join_code IS NOT NULL;
