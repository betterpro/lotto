-- Lotto Chee — Supabase / PostgreSQL schema
-- Run this once in the Supabase SQL Editor:
--   https://supabase.com/dashboard/project/thowyteqaavuewsaujot/sql

CREATE TABLE IF NOT EXISTS users (
    telegram_id        BIGINT PRIMARY KEY,
    username           TEXT,
    full_name          TEXT   NOT NULL,
    credit             FLOAT8 NOT NULL DEFAULT 0,
    is_trustee         INTEGER NOT NULL DEFAULT 0,
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
    lottery_type     TEXT    DEFAULT 'lotto_max'
);

CREATE TABLE IF NOT EXISTS participations (
    id         BIGSERIAL PRIMARY KEY,
    round_id   BIGINT  NOT NULL REFERENCES rounds(id),
    user_id    BIGINT  NOT NULL REFERENCES users(telegram_id),
    amount     FLOAT8  NOT NULL,
    shares     INTEGER DEFAULT 1,
    prize      FLOAT8  DEFAULT 0,
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
    ref_code       TEXT
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
