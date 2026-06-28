-- VR experience bookings (Zero Latency–style "book a time slot + pay with Stripe").
-- See vr_booking.py. Mirrors the idempotent statements in database.py ensure_schema().

CREATE TABLE IF NOT EXISTS vr_bookings (
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
    created_at      TEXT,
    confirmed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_vr_bookings_slot ON vr_bookings (experience_id, slot_date, slot_time);
CREATE INDEX IF NOT EXISTS idx_vr_bookings_status ON vr_bookings (status);
