import sqlite3
from typing import List, Dict, Any, Optional

DB_PATH = 'rail_debug_memory.db'

def init_db():
    """Initialize the memory database and create tables/indexes if not exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            language TEXT,
            tb_hash TEXT UNIQUE,
            tb_snippet TEXT,
            severity TEXT,
            tier_used TEXT,
            root_cause TEXT,
            suggested_fix TEXT,
            confidence REAL,
            success BOOLEAN
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON analyses(tb_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_snippet ON analyses(tb_snippet(100))')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON analyses(timestamp)')
    conn.commit()
    conn.close()

def query_similar(tb_snippet: str, limit: int = 3) -> List[Dict[str, Any]]:
    """Query similar past analyses based on tb_snippet similarity."""
    init_db()  # Ensure DB exists
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    search_term = f&quot;%{tb_snippet[:100]}%&quot;
    cursor.execute('''
        SELECT * FROM analyses 
        WHERE tb_snippet LIKE ? 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (search_term, limit))
    rows = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    results = [dict(zip(columns, row)) for row in rows]
    conn.close()
    return results

def insert_analysis(
    language: str,
    tb_hash: str,
    tb_snippet: str,
    severity: str,
    tier_used: str,
    root_cause: str,
    suggested_fix: str,
    confidence: float,
    success: bool
) -> bool:
    """Insert analysis result into memory. Returns True if inserted."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO analyses (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success))
        conn.commit()
        inserted = True
    except sqlite3.IntegrityError:
        # Duplicate tb_hash, skip
        inserted = False
    conn.close()
    return inserted
