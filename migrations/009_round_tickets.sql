-- Multiple physical tickets per round (one scan per share purchased)
-- Run in Supabase SQL Editor after 008.

ALTER TABLE rounds ADD COLUMN IF NOT EXISTS round_tickets TEXT;
