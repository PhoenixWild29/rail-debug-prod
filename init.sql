-- Init script for Rail Debug Postgres DB (users + analyses memory)
-- Run in docker-entrypoint-initdb.d/

-- Users table (monetization prep)
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    api_key TEXT UNIQUE,
    tier TEXT DEFAULT 'free' CHECK(tier IN ('free','basic','pro')),
    daily_usage INTEGER DEFAULT 0,
    monthly_usage INTEGER DEFAULT 0,
    last_daily TEXT,
    last_monthly TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_api_key ON users(api_key);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

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