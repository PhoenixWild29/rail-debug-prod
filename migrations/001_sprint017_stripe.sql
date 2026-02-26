-- Sprint 017 Migration: Stripe billing + tier constraint fix
-- Run against existing DBs. Fresh installs use init.sql which includes these.

-- Fix tier constraint to match pricing page (free/dev/team)
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_tier_check;
ALTER TABLE users ADD CONSTRAINT users_tier_check CHECK (tier IN ('free','dev','team'));

-- Add Stripe subscription tracking
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'inactive'
    CHECK (subscription_status IN ('active','inactive','past_due','canceled'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_period_end TIMESTAMP;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_users_stripe_sub ON users(stripe_subscription_id);
