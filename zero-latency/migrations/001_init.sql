-- Postgres schema for the Zero Latency VR Richmond booking app.
-- (The app also creates this automatically on startup via db.py; this file is
-- here for reference / running migrations manually.)

CREATE TABLE IF NOT EXISTS bookings (
    id              BIGSERIAL PRIMARY KEY,
    ref             TEXT UNIQUE NOT NULL,
    venue_id        TEXT NOT NULL,
    experience_id   TEXT NOT NULL,
    experience_name TEXT NOT NULL,
    slot_date       TEXT NOT NULL,          -- YYYY-MM-DD (venue local date)
    slot_time       TEXT NOT NULL,          -- HH:MM (venue local time, 24h)
    players         INTEGER NOT NULL,
    unit_price      INTEGER NOT NULL,       -- cents per player
    amount          INTEGER NOT NULL,       -- cents total
    currency        TEXT NOT NULL DEFAULT 'CAD',
    customer_name   TEXT NOT NULL,
    customer_email  TEXT NOT NULL,
    customer_phone  TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | cancelled
    stripe_session_id     TEXT,
    stripe_payment_intent TEXT,
    created_at      TEXT NOT NULL,
    confirmed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings (experience_id, slot_date, slot_time);
CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings (status);
