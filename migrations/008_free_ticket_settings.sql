-- Trustee free-ticket handling per group
-- Run in Supabase SQL Editor after 007.

ALTER TABLE groups ADD COLUMN IF NOT EXISTS free_ticket_mode TEXT NOT NULL DEFAULT 'next_round';

ALTER TABLE rounds ADD COLUMN IF NOT EXISTS free_tickets_won INTEGER NOT NULL DEFAULT 0;
ALTER TABLE rounds ADD COLUMN IF NOT EXISTS free_tickets_consumed INTEGER NOT NULL DEFAULT 0;

ALTER TABLE participations ADD COLUMN IF NOT EXISTS free_ticket_shares INTEGER NOT NULL DEFAULT 0;
ALTER TABLE participations ADD COLUMN IF NOT EXISTS free_tickets_awarded INTEGER NOT NULL DEFAULT 0;

UPDATE groups SET free_ticket_mode = 'next_round' WHERE free_ticket_mode IS NULL;
UPDATE rounds SET free_tickets_won = 0 WHERE free_tickets_won IS NULL;
UPDATE rounds SET free_tickets_consumed = 0 WHERE free_tickets_consumed IS NULL;
UPDATE participations SET free_ticket_shares = 0 WHERE free_ticket_shares IS NULL;
UPDATE participations SET free_tickets_awarded = 0 WHERE free_tickets_awarded IS NULL;
