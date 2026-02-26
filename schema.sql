CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY AUTOINCREMENT,
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