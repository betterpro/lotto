-- Lotto Chee — Supabase / PostgreSQL schema
-- Run this once in the Supabase SQL Editor:
--   https://supabase.com/dashboard/project/thowyteqaavuewsaujot/sql

CREATE TABLE IF NOT EXISTS groups (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT    NOT NULL,
    slug             TEXT    NOT NULL UNIQUE,
    trustee_user_id  BIGINT  NOT NULL,
    status               TEXT    NOT NULL DEFAULT 'active',
    etransfer_email      TEXT,
    payment_methods      TEXT    NOT NULL DEFAULT 'both',
    etransfer_min_amount FLOAT8  NOT NULL DEFAULT 25,
    free_ticket_mode     TEXT    NOT NULL DEFAULT 'next_round',
    created_at           TEXT    NOT NULL
                     DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id        BIGINT PRIMARY KEY,
    username           TEXT,
    full_name          TEXT   NOT NULL,
    credit             FLOAT8 NOT NULL DEFAULT 0,
    is_trustee         INTEGER NOT NULL DEFAULT 0,
    group_id           BIGINT  REFERENCES groups(id),
    is_platform_admin  INTEGER NOT NULL DEFAULT 0,
    invited_by         BIGINT  REFERENCES users(telegram_id),
    stripe_customer_id TEXT,
    photo_url          TEXT,
    email              TEXT,
    street             TEXT,
    city               TEXT,
    province           TEXT,
    postal_code        TEXT,
    phone              TEXT,
    declaration_category TEXT,
    agreement_accepted_at TEXT,
    created_at         TEXT   NOT NULL
                       DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

ALTER TABLE groups ADD CONSTRAINT groups_trustee_fk
    FOREIGN KEY (trustee_user_id) REFERENCES users(telegram_id);

CREATE TABLE IF NOT EXISTS group_members (
    group_id   BIGINT NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id    BIGINT NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
    role       TEXT   NOT NULL DEFAULT 'member',
    joined_at  TEXT   NOT NULL
               DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_group_members_user_id ON group_members(user_id);

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

CREATE TABLE IF NOT EXISTS user_settings (
    user_id              BIGINT  PRIMARY KEY REFERENCES users(telegram_id),
    auto_participate     INTEGER NOT NULL DEFAULT 0,
    shares_per_round     INTEGER NOT NULL DEFAULT 1,
    max_rounds_per_month INTEGER NOT NULL DEFAULT 4,
    preferred_day        INTEGER,
    lottery_preference   TEXT    NOT NULL DEFAULT 'both',
    notif_new_round      INTEGER NOT NULL DEFAULT 1,
    notif_reminder       INTEGER NOT NULL DEFAULT 1,
    notif_ticket         INTEGER NOT NULL DEFAULT 1,
    notif_results        INTEGER NOT NULL DEFAULT 1,
    updated_at           TEXT    NOT NULL
                         DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS rounds (
    id               BIGSERIAL PRIMARY KEY,
    status           TEXT    NOT NULL DEFAULT 'open',
    pool             FLOAT8  NOT NULL DEFAULT 0,
    draw_date        TEXT,
    winner_id        BIGINT  REFERENCES users(telegram_id),
    ticket_ref       TEXT,
    opened_at        TEXT    NOT NULL
                     DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    closed_at        TEXT,
    drawn_at         TEXT,
    jackpot          INTEGER DEFAULT 0,
    tickets_target   INTEGER DEFAULT 25,
    price_per_share  FLOAT8  DEFAULT 5,
    winning_numbers  TEXT,
    bonus_number     INTEGER,
    ticket_numbers   TEXT,
    ticket_image     TEXT,
    round_tickets    TEXT,
    lottery_type          TEXT    DEFAULT 'lotto_max',
    free_tickets_won      INTEGER NOT NULL DEFAULT 0,
    free_tickets_consumed INTEGER NOT NULL DEFAULT 0,
    group_id              BIGINT  NOT NULL REFERENCES groups(id)
);

CREATE TABLE IF NOT EXISTS participations (
    id         BIGSERIAL PRIMARY KEY,
    round_id   BIGINT  NOT NULL REFERENCES rounds(id),
    user_id    BIGINT  NOT NULL REFERENCES users(telegram_id),
    amount     FLOAT8  NOT NULL,
    shares              INTEGER DEFAULT 1,
    free_ticket_shares  INTEGER NOT NULL DEFAULT 0,
    free_tickets_awarded INTEGER NOT NULL DEFAULT 0,
    prize               FLOAT8  DEFAULT 0,
    created_at TEXT    NOT NULL
               DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    UNIQUE(round_id, user_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(telegram_id),
    type       TEXT   NOT NULL,
    amount     FLOAT8 NOT NULL,
    note       TEXT,
    group_id   BIGINT REFERENCES groups(id),
    created_at TEXT   NOT NULL
               DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS deposit_requests (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(telegram_id),
    amount         FLOAT8 NOT NULL,
    status         TEXT   NOT NULL DEFAULT 'pending',
    trustee_note   TEXT,
    created_at     TEXT   NOT NULL
                   DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    resolved_at    TEXT,
    payment_method TEXT   DEFAULT 'etransfer',
    ref_code       TEXT,
    group_id       BIGINT REFERENCES groups(id)
);

CREATE TABLE IF NOT EXISTS etransfer_email_receipts (
    id                   BIGSERIAL PRIMARY KEY,
    message_id           TEXT UNIQUE,
    payment_notification TEXT UNIQUE,
    sender_email         TEXT,
    amount               FLOAT8,
    deposit_request_id   BIGINT REFERENCES deposit_requests(id),
    created_at           TEXT NOT NULL
                         DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS')
);

CREATE TABLE IF NOT EXISTS stripe_subscriptions (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(telegram_id),
    stripe_sub_id TEXT   NOT NULL UNIQUE,
    amount        FLOAT8 NOT NULL,
    status        TEXT   NOT NULL DEFAULT 'active',
    created_at    TEXT   NOT NULL
                  DEFAULT to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI:SS'),
    updated_at    TEXT
);
