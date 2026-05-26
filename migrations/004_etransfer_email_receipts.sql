-- Track Interac notification emails so a single e-transfer cannot credit twice.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;

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
