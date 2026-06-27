-- Subscription payment on trustee applications (pay first, auto-approve after 24h)
ALTER TABLE trustee_applications ADD COLUMN IF NOT EXISTS stripe_sub_id TEXT;
ALTER TABLE trustee_applications ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'none';
ALTER TABLE trustee_applications ADD COLUMN IF NOT EXISTS paid_at TEXT;
ALTER TABLE trustee_applications ADD COLUMN IF NOT EXISTS auto_approve_at TEXT;
