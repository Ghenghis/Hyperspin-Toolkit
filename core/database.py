"""SQLite database engine for tracking ROMs, emulators, media, backups, audits."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from core.config import get as cfg_get
from core.logger import get_logger, audit

log = get_logger("database")

_SCHEMA_VERSION = 2

_SCHEMA_SQL = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Systems (e.g., "Nintendo Entertainment System", "Sega Genesis")
CREATE TABLE IF NOT EXISTS systems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    folder_name TEXT,
    xml_path TEXT,
    emulator_name TEXT,
    rom_path TEXT,
    media_path TEXT,
    rom_count INTEGER DEFAULT 0,
    media_count INTEGER DEFAULT 0,
    health_score REAL DEFAULT 0.0,
    last_audit TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ROMs
CREATE TABLE IF NOT EXISTS roms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL REFERENCES systems(id),
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    extension TEXT,
    sha256 TEXT,
    crc32 TEXT,
    status TEXT DEFAULT 'unknown',       -- ok, missing, corrupt, duplicate, extra
    in_database INTEGER DEFAULT 0,       -- present in HyperSpin XML?
    last_verified TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_roms_system ON roms(system_id);
CREATE INDEX IF NOT EXISTS idx_roms_sha256 ON roms(sha256);

-- Emulators
CREATE TABLE IF NOT EXISTS emulators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    folder_name TEXT,
    exe_path TEXT,
    version TEXT,
    last_known_version TEXT,
    is_healthy INTEGER DEFAULT 0,
    last_check TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Media assets
CREATE TABLE IF NOT EXISTS media_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id INTEGER NOT NULL REFERENCES systems(id),
    game_name TEXT,
    media_type TEXT NOT NULL,            -- theme, wheel, video, artwork, bezel, fanart
    filepath TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    status TEXT DEFAULT 'ok',            -- ok, missing, corrupt, orphaned
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_media_system ON media_assets(system_id);

-- Backups
CREATE TABLE IF NOT EXISTS backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_type TEXT NOT NULL,           -- full, incremental, selective
    target TEXT NOT NULL,                -- what was backed up
    backup_path TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    file_count INTEGER DEFAULT 0,
    hash_manifest TEXT,
    status TEXT DEFAULT 'created',       -- created, verified, corrupt, restored
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Update history
CREATE TABLE IF NOT EXISTS update_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    program_name TEXT NOT NULL,
    old_version TEXT,
    new_version TEXT,
    snapshot_path TEXT,
    status TEXT DEFAULT 'pending',       -- pending, applied, tested, committed, rolled_back, failed
    applied_at TEXT,
    tested_at TEXT,
    committed_at TEXT,
    rolled_back_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Audit events (queryable complement to the JSONL audit trail)
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT,
    severity TEXT DEFAULT 'INFO',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);

-- AI conversation memory
CREATE TABLE IF NOT EXISTS ai_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    role TEXT NOT NULL,                  -- user, assistant, system
    content TEXT NOT NULL,
    model TEXT,
    provider TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Plugin registry
CREATE TABLE IF NOT EXISTS plugins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    version TEXT,
    author TEXT DEFAULT '',
    description TEXT DEFAULT '',
    license TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',              -- JSON array of tag strings
    state TEXT DEFAULT 'DISCOVERED',     -- DISCOVERED, LOADED, ENABLED, DISABLED, ERROR
    enabled INTEGER DEFAULT 0,
    error TEXT,
    plugin_style TEXT DEFAULT 'class',   -- class or legacy
    file_path TEXT,
    config_defaults TEXT DEFAULT '{}',   -- JSON default config
    installed_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_enabled_at TEXT,
    last_disabled_at TEXT
);

-- Plugin configuration key-value store
CREATE TABLE IF NOT EXISTS plugin_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(plugin_name, key)
);
CREATE INDEX IF NOT EXISTS idx_plugin_config_name ON plugin_config(plugin_name);

-- Plugin dependencies
CREATE TABLE IF NOT EXISTS plugin_dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT NOT NULL,
    depends_on TEXT NOT NULL,
    version_spec TEXT DEFAULT '*',       -- semver spec e.g. '>=1.0'
    required INTEGER DEFAULT 1,          -- 1=hard dep, 0=optional
    UNIQUE(plugin_name, depends_on)
);
CREATE INDEX IF NOT EXISTS idx_plugin_deps_name ON plugin_dependencies(plugin_name);

-- Plugin registered hooks
CREATE TABLE IF NOT EXISTS plugin_hooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT NOT NULL,
    hook_type TEXT NOT NULL,             -- event, route, tool, command
    hook_name TEXT NOT NULL,             -- e.g. 'audit.complete', '/api/myplugin', 'my_tool'
    details TEXT DEFAULT '{}',           -- JSON metadata
    registered_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plugin_hooks_name ON plugin_hooks(plugin_name);

-- Plugin event log
CREATE TABLE IF NOT EXISTS plugin_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_name TEXT NOT NULL,
    event_type TEXT NOT NULL,            -- loaded, enabled, disabled, unloaded, error, config_changed
    details TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_plugin_events_name ON plugin_events(plugin_name);
"""


def _db_path() -> Path:
    p = Path(cfg_get("database.path", "data/toolkit.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def init_db() -> None:
    """Initialize the database schema."""
    db = _db_path()
    log.info("Initializing database at %s", db)
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(_SCHEMA_SQL)
        existing = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        if existing is None or existing < _SCHEMA_VERSION:
            conn.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
            conn.commit()
    log.info("Database initialized (schema v%d)", _SCHEMA_VERSION)
    audit("db_init", str(db), {"schema_version": _SCHEMA_VERSION})


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for a database connection with row factory."""
    db = _db_path()
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a query and return results as list of dicts."""
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def execute_many(sql: str, params_list: list[tuple]) -> int:
    """Execute a parameterized query for many rows. Return rowcount."""
    with get_conn() as conn:
        cursor = conn.executemany(sql, params_list)
        return cursor.rowcount


def insert(table: str, data: dict[str, Any]) -> int:
    """Insert a dict into a table. Return lastrowid."""
    cols = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    with get_conn() as conn:
        cursor = conn.execute(sql, tuple(data.values()))
        return cursor.lastrowid
