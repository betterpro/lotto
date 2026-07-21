-- Group-scoped WHEN/THEN notification rules.
-- Rules are evaluated by the trusted FastAPI backend, not through the Data API.

DROP TABLE IF EXISTS notif_templates;

CREATE TABLE IF NOT EXISTS notification_rules (
    id              BIGSERIAL PRIMARY KEY,
    group_id        BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    condition_field TEXT NOT NULL DEFAULT 'credit'
                    CHECK (condition_field = 'credit'),
    operator        TEXT NOT NULL DEFAULT 'lt'
                    CHECK (operator IN ('lt', 'lte', 'gt', 'gte')),
    threshold       FLOAT8 NOT NULL CHECK (threshold >= 0),
    message         TEXT NOT NULL CHECK (char_length(message) BETWEEN 1 AND 3500),
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_by      BIGINT NOT NULL REFERENCES users(telegram_id),
    created_at      TEXT NOT NULL
                    DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    updated_at      TEXT NOT NULL
                    DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE INDEX IF NOT EXISTS idx_notification_rules_group_enabled
    ON notification_rules (group_id, enabled);

CREATE TABLE IF NOT EXISTS notification_rule_states (
    rule_id           BIGINT NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
    user_id           BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    is_matching       INTEGER NOT NULL DEFAULT 0 CHECK (is_matching IN (0, 1)),
    match_cycle       BIGINT NOT NULL DEFAULT 0,
    last_value        FLOAT8,
    last_evaluated_at TEXT,
    last_sent_at      TEXT,
    PRIMARY KEY (rule_id, user_id)
);

CREATE TABLE IF NOT EXISTS notification_deliveries (
    id             BIGSERIAL PRIMARY KEY,
    rule_id        BIGINT NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
    group_id       BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id        BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    match_cycle    BIGINT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending', 'sent', 'failed')),
    rendered_text  TEXT NOT NULL,
    error          TEXT,
    created_at     TEXT NOT NULL
                   DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    sent_at        TEXT,
    UNIQUE (rule_id, user_id, match_cycle)
);

CREATE INDEX IF NOT EXISTS idx_notification_deliveries_group_created
    ON notification_deliveries (group_id, created_at DESC);

ALTER TABLE notification_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_rule_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE notification_deliveries ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE notification_rules FROM anon, authenticated;
REVOKE ALL ON TABLE notification_rule_states FROM anon, authenticated;
REVOKE ALL ON TABLE notification_deliveries FROM anon, authenticated;
REVOKE ALL ON SEQUENCE notification_rules_id_seq FROM anon, authenticated;
REVOKE ALL ON SEQUENCE notification_deliveries_id_seq FROM anon, authenticated;
