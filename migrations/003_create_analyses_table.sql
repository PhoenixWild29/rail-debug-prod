CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    language VARCHAR(50),
    tier_used VARCHAR(20),
    severity VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);