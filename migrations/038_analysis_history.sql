-- RAIL-039: Add full analysis detail columns to user-facing Postgres analyses table
-- Target: migration 003 Postgres table (NOT the SQLite memory table in core/memory.py)

ALTER TABLE analyses ADD COLUMN IF NOT EXISTS traceback_text TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS error_type VARCHAR(200);
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS root_cause TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS suggested_fix TEXT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS confidence FLOAT;
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS model_used VARCHAR(100);
ALTER TABLE analyses ADD COLUMN IF NOT EXISTS title VARCHAR(200);

CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id);