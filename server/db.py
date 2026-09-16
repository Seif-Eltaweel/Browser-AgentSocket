"""
AgentSocket - SQLite Embedded Database Engine (Spec 25)
High-performance transactional storage running in WAL (Write-Ahead Logging) mode.
Replaces flat-file index.json with atomic O(1) indexed session metadata and events.
"""

import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "agentsocket.db")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Ensures WAL mode and all core tables/indexes exist on the connection."""
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")

    # 1. Sessions Table (Replaces index.json)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        tab_group_id INTEGER,
        tab_group_name TEXT,
        group_color TEXT,
        agent_name TEXT,
        mode TEXT DEFAULT 'direct',
        status TEXT DEFAULT 'active',
        start_time REAL NOT NULL,
        end_time REAL,
        duration_ms REAL DEFAULT 0.0,
        event_count INTEGER DEFAULT 0,
        action_count INTEGER DEFAULT 0,
        takeover_count INTEGER DEFAULT 0,
        session_path TEXT,
        artifacts_count INTEGER DEFAULT 0,
        end_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON sessions(start_time DESC);")

    # 2. Events Stream Index Table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT UNIQUE,
        session_id TEXT REFERENCES sessions(session_id) ON DELETE CASCADE,
        event_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        duration_ms REAL,
        payload_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp);")

    # 3. Subskills SOP Catalog Table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS subskills (
        slug TEXT PRIMARY KEY,
        display_title TEXT NOT NULL,
        description TEXT,
        tags TEXT,
        times_referenced INTEGER DEFAULT 0,
        playbook_path TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)


def init_db(db_path: str | None = None) -> None:
    """Initializes SQLite tables and enables WAL mode."""
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with get_connection(target_path) as conn:
        _ensure_schema(conn)


@contextmanager
def get_connection(db_path: str | None = None):
    """Provides a transactional database connection with automatic commit/rollback."""
    target_path = db_path or DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    needs_init = not os.path.exists(target_path) or os.path.getsize(target_path) == 0
    conn = sqlite3.connect(target_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    if needs_init:
        _ensure_schema(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

