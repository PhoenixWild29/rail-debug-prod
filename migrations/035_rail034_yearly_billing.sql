-- RAIL-034: Add billing_period column to users table
-- Tracks whether user is on monthly or yearly billing cycle
ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_period TEXT DEFAULT 'monthly';
