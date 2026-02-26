-- Init script for Rail Debug Postgres DB (users + analyses memory)
-- Run in docker-entrypoint-initdb.d/

-- Users table (monetization prep)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    api_key TEXT UNIQUE,
    tier TEXT DEFAULT 'free' CHECK(tier IN ('free','dev','team')),
    daily_usage INTEGER DEFAULT 0,
    monthly_usage INTEGER DEFAULT 0,
    last_daily TEXT,
    last_monthly TEXT,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    subscription_status TEXT DEFAULT 'inactive' CHECK(subscription_status IN ('active','inactive','past_due','canceled')),
    billing_period_end TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_users_stripe_sub ON users(stripe_subscription_id);

-- Analyses memory table (learning loop)
CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    language TEXT,
    tb_hash TEXT UNIQUE,
    tb_snippet TEXT,
    severity TEXT,
    tier_used TEXT,
    root_cause TEXT,
    suggested_fix TEXT,
    confidence DOUBLE PRECISION,
    success BOOLEAN DEFAULT false,
    repo_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_hash ON analyses(tb_hash);
CREATE INDEX IF NOT EXISTS idx_analyses_snippet ON analyses(tb_snippet(100));
CREATE INDEX IF NOT EXISTS idx_analyses_time ON analyses(timestamp);
CREATE INDEX IF NOT EXISTS idx_analyses_repo ON analyses(repo_id);

-- Waitlist table for marketing funnel
CREATE TABLE IF NOT EXISTS waitlist (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    first_name TEXT,
    tier_interest TEXT DEFAULT 'free',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source TEXT DEFAULT 'marketing-site'
);
CREATE INDEX IF NOT EXISTS idx_waitlist_email ON waitlist(email);
CREATE INDEX IF NOT EXISTS idx_waitlist_tier ON waitlist(tier_interest);