import os
import sqlite3
try:
    import psycopg
    from psycopg.rows import dict_row
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

from typing import List, Dict, Any, Optional

DATABASE_URL = os.getenv('DATABASE_URL')
IS_POSTGRES = HAS_POSTGRES and DATABASE_URL and DATABASE_URL.startswith('postgresql://')
DB_PATH = os.getenv('SQLITE_PATH', 'rail_debug_memory.db')

def init_db():
    \"\"\"Initialize the memory database. Idempotent.\"\"\"

    if IS_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        cursor = conn.cursor()
        # Tables created by init.sql in Docker, but indexes etc.
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analyses_hash ON analyses(tb_hash)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analyses_snippet ON analyses(tb_snippet(100))
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analyses_time ON analyses(timestamp)
        ''')
        # Migrate repo_id if missing (unlikely)
        cursor.execute('''
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'analyses' AND column_name = 'repo_id'
        ''')
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE analyses ADD COLUMN repo_id TEXT')
        conn.commit()
        conn.close()
    else:
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
                success INTEGER,
                repo_id TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_hash ON analyses(tb_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_snippet ON analyses(tb_snippet)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_time ON analyses(timestamp)')
        # Migrate repo_id
        cursor.execute("PRAGMA table_info(analyses)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'repo_id' not in columns:
            cursor.execute("ALTER TABLE analyses ADD COLUMN repo_id TEXT")
        conn.commit()
        conn.close()

def query_similar(tb_snippet: str, repo_id: Optional[str] = None, limit: int = 3) -> List[Dict[str, Any]]:
    \"\"\"Query similar past analyses.\"\"\"

    search_term = f'%{tb_snippet[:100]}%'
    if IS_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        cursor = conn.cursor()
        if repo_id:
            cursor.execute('''
                SELECT * FROM analyses 
                WHERE tb_snippet LIKE $1 AND (repo_id = $2 OR repo_id IS NULL OR repo_id = '')
                ORDER BY CASE WHEN (repo_id = $2 OR repo_id IS NULL OR repo_id = '') THEN 0 ELSE 1 END, timestamp DESC 
                LIMIT $3
            ''', (search_term, repo_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM analyses WHERE tb_snippet LIKE $1 ORDER BY timestamp DESC LIMIT $2
            ''', (search_term, limit))
        rows = cursor.fetchall()
        results = list(rows)
        conn.close()
        return results
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if repo_id:
            cursor.execute('''
                SELECT * FROM analyses 
                WHERE tb_snippet LIKE ? AND (repo_id = ? OR repo_id IS NULL OR repo_id = '')
                ORDER BY CASE WHEN (repo_id = ? OR repo_id IS NULL OR repo_id = '') THEN 0 ELSE 1 END, timestamp DESC 
                LIMIT ?
            ''', (search_term, repo_id, repo_id, limit))
        else:
            cursor.execute('''
                SELECT * FROM analyses WHERE tb_snippet LIKE ? ORDER BY timestamp DESC LIMIT ?
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
    success: bool,
    repo_id: Optional[str] = None
) -> bool:
    \"\"\"Insert analysis result. Returns True if inserted (new).\"\"\"

    success_int = 1 if success else 0
    if IS_POSTGRES:
        try:
            conn = psycopg.connect(DATABASE_URL)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO analyses (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success, repo_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''', (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success, repo_id))
            conn.commit()
            inserted = True
        except psycopg.errors.UniqueViolation:
            inserted = False
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO analyses (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success, repo_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (language, tb_hash, tb_snippet, severity, tier_used, root_cause, suggested_fix, confidence, success_int, repo_id))
            conn.commit()
            inserted = True
        except sqlite3.IntegrityError:
            inserted = False
        conn.close()
    return inserted

def get_repo_stats(repo_id: Optional[str] = None) -> Dict[str, Any]:
    \"\"\"Get analysis stats.\"\"\"

    if IS_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        cursor = conn.cursor()
        params = []
        if repo_id:
            where_clause = "WHERE repo_id = $1 OR repo_id IS NULL OR repo_id = ''"
            params = [repo_id]
            sql = f'''
                SELECT 
                    COUNT(*) as total,
                    AVG(confidence)::numeric(4,2) as avg_conf,
                    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successes,
                    string_agg(DISTINCT severity, ', ') as severities
                FROM analyses {where_clause}
            '''
            cursor.execute(sql, params)
        else:
            cursor.execute('''
                SELECT 
                    COUNT(*) as total,
                    AVG(confidence)::numeric(4,2) as avg_conf,
                    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successes,
                    string_agg(DISTINCT severity, ', ') as severities
                FROM analyses
            ''')
        row = cursor.fetchone()
        stats = {
            "total_analyses": row['total'] if row else 0,
            "avg_confidence": float(row['avg_conf']) if row and row['avg_conf'] else 0.0,
            "successful_fixes": row['successes'] if row else 0,
            "severities": row['severities'].split(', ') if row and row['severities'] else [],
            "success_rate": round((row['successes'] / row['total']) if row and row['total'] > 0 else 0.0, 2)
        }
        conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        params = []
        if repo_id:
            where_clause = "WHERE repo_id = ? OR repo_id IS NULL OR repo_id = ''"
            params = [repo_id]
        else:
            where_clause = ""
        cursor.execute(f'''
            SELECT 
                COUNT(*) as total,
                AVG(confidence) as avg_conf,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                GROUP_CONCAT(DISTINCT severity) as severities
            FROM analyses {where_clause}
        ''', params)
        row = cursor.fetchone()
        stats = {
            "total_analyses": row[0] if row else 0,
            "avg_confidence": round(float(row[1]) if row and row[1] else 0.0, 2),
            "successful_fixes": row[2] if row else 0,
            "severities": row[3].split(",") if row and row[3] else [],
            "success_rate": round((row[2] / row[0]) if row and row[0] > 0 else 0.0, 2)
        }
        conn.close()
    return stats