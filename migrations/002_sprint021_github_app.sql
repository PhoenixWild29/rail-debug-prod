-- Sprint 021: GitHub App tables + user columns

ALTER TABLE users ADD COLUMN IF NOT EXISTS github_installation_id BIGINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS github_username TEXT;

CREATE TABLE IF NOT EXISTS github_installations (
    id SERIAL PRIMARY KEY,
    installation_id BIGINT UNIQUE NOT NULL,
    account_login TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'User',
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    active BOOLEAN DEFAULT true,
    installed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uninstalled_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS github_analyses (
    id SERIAL PRIMARY KEY,
    installation_id BIGINT NOT NULL,
    repo_full_name TEXT NOT NULL,
    workflow_run_id BIGINT,
    head_sha TEXT,
    traceback_snippet TEXT,
    analysis_result JSONB,
    comment_posted BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);