-- Per-group payment methods and e-transfer minimum
-- Run in Supabase SQL Editor after 006.

ALTER TABLE groups ADD COLUMN IF NOT EXISTS payment_methods TEXT NOT NULL DEFAULT 'both';
ALTER TABLE groups ADD COLUMN IF NOT EXISTS etransfer_min_amount FLOAT8 NOT NULL DEFAULT 25;

UPDATE groups SET payment_methods = 'both' WHERE payment_methods IS NULL;
UPDATE groups SET etransfer_min_amount = 25 WHERE etransfer_min_amount IS NULL;
