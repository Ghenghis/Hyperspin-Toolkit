"""
M62 -- Agent Memory, Learning & Knowledge Base

Provides:
  - Persistent agent memory (SQLite agent_memory table)
  - Key observation storage from audits and user corrections
  - Session history with searchable context
  - Emulator quirks database (learned from troubleshooting)
  - ROM compatibility notes
  - User preference learning
  - Adaptive recommendation tracking (accept/reject)
  - Knowledge base search and retrieval
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent_memory")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "agent_memory.db"


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class Memory:
    """A single memory entry — observation, fact, or learned knowledge."""
    memory_id: int = 0
    category: str = ""        # observation, quirk, compatibility, preference, correction, tip
    subject: str = ""         # system, emulator, game, or general topic
    key: str = ""             # concise identifier
    value: str = ""           # the knowledge content
    confidence: float = 1.0   # 0.0-1.0 how reliable this knowledge is
    source: str = ""          # audit, user, troubleshoot, community
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    last_accessed: str = ""
    tags: str = ""            # comma-separated tags
    related_memories: str = "" # comma-separated memory IDs

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tags_list"] = [t.strip() for t in self.tags.split(",") if t.strip()]
        return d


@dataclass
class SessionEntry:
    """A session history entry — records what the agent did and found."""
    entry_id: int = 0
    session_id: str = ""
    timestamp: str = ""
    action: str = ""          # scan, repair, recommend, search, etc.
    engine: str = ""          # which engine performed the action
    input_summary: str = ""   # what was requested
    output_summary: str = ""  # what was found/done
    systems_involved: str = "" # comma-separated system names
    items_processed: int = 0
    issues_found: int = 0
    issues_fixed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    """Tracks a recommendation and whether user accepted/rejected it."""
    rec_id: int = 0
    timestamp: str = ""
    category: str = ""        # repair, config, download, cleanup
    subject: str = ""         # system or topic
    recommendation: str = ""  # what was recommended
    reason: str = ""          # why
    accepted: Optional[bool] = None  # None=pending, True=accepted, False=rejected
    feedback: str = ""        # optional user feedback
    effectiveness: float = 0  # 0-1 how effective the rec was after acceptance

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    """Create/open the agent memory SQLite database."""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subject TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            access_count INTEGER DEFAULT 0,
            last_accessed TEXT,
            tags TEXT DEFAULT '',
            related_memories TEXT DEFAULT '',
            UNIQUE(category, subject, key)
        );

        CREATE TABLE IF NOT EXISTS session_history (
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            action TEXT,
            engine TEXT,
            input_summary TEXT,
            output_summary TEXT,
            systems_involved TEXT DEFAULT '',
            items_processed INTEGER DEFAULT 0,
            issues_found INTEGER DEFAULT 0,
            issues_fixed INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS recommendations (
            rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT,
            subject TEXT,
            recommendation TEXT NOT NULL,
            reason TEXT,
            accepted INTEGER,
            feedback TEXT DEFAULT '',
            effectiveness REAL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_mem_category ON memories(category);
        CREATE INDEX IF NOT EXISTS idx_mem_subject ON memories(subject);
        CREATE INDEX IF NOT EXISTS idx_mem_tags ON memories(tags);
        CREATE INDEX IF NOT EXISTS idx_session_id ON session_history(session_id);
        CREATE INDEX IF NOT EXISTS idx_session_ts ON session_history(timestamp);
        CREATE INDEX IF NOT EXISTS idx_rec_category ON recommendations(category);
        CREATE INDEX IF NOT EXISTS idx_rec_accepted ON recommendations(accepted);

        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
            key, value, subject, tags,
            content='memories', content_rowid='memory_id'
        );

        CREATE TRIGGER IF NOT EXISTS mem_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, key, value, subject, tags)
            VALUES (new.memory_id, new.key, new.value, new.subject, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS mem_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, subject, tags)
            VALUES ('delete', old.memory_id, old.key, old.value, old.subject, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS mem_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, key, value, subject, tags)
            VALUES ('delete', old.memory_id, old.key, old.value, old.subject, old.tags);
            INSERT INTO memories_fts(rowid, key, value, subject, tags)
            VALUES (new.memory_id, new.key, new.value, new.subject, new.tags);
        END;
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Memory CRUD
# -----------------------------------------------------------------------

def store_memory(category: str, subject: str, key: str, value: str,
                 confidence: float = 1.0, source: str = "",
                 tags: str = "") -> Memory:
    """Store or update a memory entry."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        # Check if exists
        existing = conn.execute(
            "SELECT memory_id, access_count FROM memories WHERE category=? AND subject=? AND key=?",
            (category, subject, key)
        ).fetchone()

        if existing:
            conn.execute("""
                UPDATE memories SET value=?, confidence=?, source=?, updated_at=?, tags=?
                WHERE memory_id=?
            """, (value, confidence, source, now, tags, existing[0]))
            conn.commit()
            mem_id = existing[0]
            logger.debug("Updated memory %d: %s/%s/%s", mem_id, category, subject, key)
        else:
            cur = conn.execute("""
                INSERT INTO memories (category, subject, key, value, confidence, source,
                                      created_at, updated_at, tags)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (category, subject, key, value, confidence, source, now, now, tags))
            conn.commit()
            mem_id = cur.lastrowid
            logger.debug("Created memory %d: %s/%s/%s", mem_id, category, subject, key)

        return Memory(
            memory_id=mem_id, category=category, subject=subject,
            key=key, value=value, confidence=confidence, source=source,
            created_at=now, updated_at=now, tags=tags,
        )
    finally:
        conn.close()


def recall_memory(category: str = "", subject: str = "",
                  key: str = "") -> Optional[Memory]:
    """Recall a specific memory by category/subject/key."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM memories WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if subject:
            sql += " AND subject=?"
            params.append(subject)
        if key:
            sql += " AND key=?"
            params.append(key)
        sql += " ORDER BY confidence DESC, updated_at DESC LIMIT 1"

        row = conn.execute(sql, params).fetchone()
        if not row:
            return None

        mem = _row_to_memory(row, conn)

        # Update access stats
        conn.execute("""
            UPDATE memories SET access_count = access_count + 1,
                   last_accessed = ? WHERE memory_id = ?
        """, (datetime.now(timezone.utc).isoformat(), mem.memory_id))
        conn.commit()

        return mem
    finally:
        conn.close()


def search_memories(query: str, category: str = "",
                    subject: str = "", limit: int = 20) -> List[Memory]:
    """Full-text search across all memories."""
    conn = _ensure_db()
    try:
        if query:
            # FTS5 search
            sql = """
                SELECT m.* FROM memories m
                JOIN memories_fts f ON m.memory_id = f.rowid
                WHERE memories_fts MATCH ?
            """
            params: list = [query]
        else:
            sql = "SELECT * FROM memories WHERE 1=1"
            params = []

        if category:
            sql += " AND m.category=?" if query else " AND category=?"
            params.append(category)
        if subject:
            sql += " AND m.subject=?" if query else " AND subject=?"
            params.append(subject)

        sql += " ORDER BY confidence DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_memory(r, conn) for r in rows]
    except Exception as e:
        logger.warning("Memory search error: %s", e)
        # Fallback to LIKE search
        conn2 = _ensure_db()
        try:
            sql = "SELECT * FROM memories WHERE (key LIKE ? OR value LIKE ?)"
            params = [f"%{query}%", f"%{query}%"]
            if category:
                sql += " AND category=?"
                params.append(category)
            if subject:
                sql += " AND subject=?"
                params.append(subject)
            sql += " ORDER BY confidence DESC LIMIT ?"
            params.append(limit)
            rows = conn2.execute(sql, params).fetchall()
            return [_row_to_memory(r, conn2) for r in rows]
        finally:
            conn2.close()
    finally:
        conn.close()


def delete_memory(memory_id: int) -> bool:
    """Delete a memory by ID."""
    conn = _ensure_db()
    try:
        result = conn.execute("DELETE FROM memories WHERE memory_id=?", (memory_id,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def get_memory_stats() -> Dict[str, Any]:
    """Get memory database statistics."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        by_category = conn.execute(
            "SELECT category, COUNT(*) FROM memories GROUP BY category"
        ).fetchall()
        by_subject = conn.execute(
            "SELECT subject, COUNT(*) FROM memories GROUP BY subject ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall()
        most_accessed = conn.execute(
            "SELECT key, subject, access_count FROM memories ORDER BY access_count DESC LIMIT 10"
        ).fetchall()
        sessions = conn.execute("SELECT COUNT(DISTINCT session_id) FROM session_history").fetchone()[0]
        recs = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        accepted = conn.execute("SELECT COUNT(*) FROM recommendations WHERE accepted=1").fetchone()[0]
        rejected = conn.execute("SELECT COUNT(*) FROM recommendations WHERE accepted=0").fetchone()[0]

        return {
            "total_memories": total,
            "by_category": {r[0]: r[1] for r in by_category},
            "top_subjects": {r[0]: r[1] for r in by_subject},
            "most_accessed": [{"key": r[0], "subject": r[1], "count": r[2]} for r in most_accessed],
            "total_sessions": sessions,
            "total_recommendations": recs,
            "accepted_recommendations": accepted,
            "rejected_recommendations": rejected,
            "acceptance_rate": round(accepted / recs * 100, 1) if recs > 0 else 0,
        }
    finally:
        conn.close()


def _row_to_memory(row, conn) -> Memory:
    cols = [d[0] for d in conn.execute("SELECT * FROM memories LIMIT 0").description]
    d = dict(zip(cols, row))
    return Memory(**d)


# -----------------------------------------------------------------------
# Quirks database (emulator-specific issues)
# -----------------------------------------------------------------------

def store_quirk(emulator: str, quirk_key: str, description: str,
                workaround: str = "", source: str = "troubleshoot") -> Memory:
    """Store an emulator quirk/known issue."""
    value = json.dumps({"description": description, "workaround": workaround})
    return store_memory(
        category="quirk", subject=emulator, key=quirk_key,
        value=value, source=source, tags="quirk,emulator"
    )


def get_quirks(emulator: str = "") -> List[Dict]:
    """Get all known quirks, optionally filtered by emulator."""
    mems = search_memories("", category="quirk", subject=emulator, limit=100)
    results = []
    for m in mems:
        try:
            data = json.loads(m.value)
        except json.JSONDecodeError:
            data = {"description": m.value, "workaround": ""}
        results.append({
            "emulator": m.subject,
            "key": m.key,
            "description": data.get("description", ""),
            "workaround": data.get("workaround", ""),
            "confidence": m.confidence,
            "source": m.source,
        })
    return results


# -----------------------------------------------------------------------
# ROM compatibility notes
# -----------------------------------------------------------------------

def store_compatibility(game: str, system: str, emulator: str,
                        status: str, notes: str = "",
                        source: str = "user") -> Memory:
    """Store a ROM compatibility note."""
    value = json.dumps({
        "emulator": emulator, "status": status, "notes": notes
    })
    return store_memory(
        category="compatibility", subject=system, key=f"{game}|{emulator}",
        value=value, source=source, tags="compatibility,rom"
    )


def get_compatibility(game: str = "", system: str = "",
                      emulator: str = "") -> List[Dict]:
    """Get ROM compatibility notes."""
    query = game or emulator or ""
    mems = search_memories(query, category="compatibility",
                           subject=system, limit=50)
    results = []
    for m in mems:
        try:
            data = json.loads(m.value)
        except json.JSONDecodeError:
            data = {}
        results.append({
            "game_emulator": m.key,
            "system": m.subject,
            "emulator": data.get("emulator", ""),
            "status": data.get("status", ""),
            "notes": data.get("notes", ""),
            "confidence": m.confidence,
        })
    return results


# -----------------------------------------------------------------------
# User preferences
# -----------------------------------------------------------------------

def store_preference(key: str, value: str, source: str = "user") -> Memory:
    """Store a user preference."""
    return store_memory(
        category="preference", subject="user", key=key,
        value=value, source=source, tags="preference"
    )


def get_preference(key: str, default: str = "") -> str:
    """Get a user preference value."""
    mem = recall_memory(category="preference", subject="user", key=key)
    return mem.value if mem else default


def get_all_preferences() -> Dict[str, str]:
    """Get all stored user preferences."""
    mems = search_memories("", category="preference", limit=200)
    return {m.key: m.value for m in mems}


# -----------------------------------------------------------------------
# Session history
# -----------------------------------------------------------------------

def log_session_action(session_id: str, action: str, engine: str = "",
                       input_summary: str = "", output_summary: str = "",
                       systems: str = "", items: int = 0,
                       issues_found: int = 0, issues_fixed: int = 0) -> int:
    """Log an action in the current session."""
    conn = _ensure_db()
    try:
        cur = conn.execute("""
            INSERT INTO session_history
            (session_id, timestamp, action, engine, input_summary, output_summary,
             systems_involved, items_processed, issues_found, issues_fixed)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (session_id, datetime.now(timezone.utc).isoformat(), action, engine,
              input_summary, output_summary, systems, items, issues_found, issues_fixed))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_session_history(session_id: str = "", limit: int = 50) -> List[SessionEntry]:
    """Get session history entries."""
    conn = _ensure_db()
    try:
        if session_id:
            rows = conn.execute(
                "SELECT * FROM session_history WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM session_history ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM session_history LIMIT 0").description]
        return [SessionEntry(**dict(zip(cols, r))) for r in rows]
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Recommendation tracking
# -----------------------------------------------------------------------

def store_recommendation(category: str, subject: str,
                         recommendation: str, reason: str = "") -> int:
    """Store a new recommendation."""
    conn = _ensure_db()
    try:
        cur = conn.execute("""
            INSERT INTO recommendations (timestamp, category, subject, recommendation, reason)
            VALUES (?,?,?,?,?)
        """, (datetime.now(timezone.utc).isoformat(), category, subject,
              recommendation, reason))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def respond_to_recommendation(rec_id: int, accepted: bool,
                              feedback: str = "",
                              effectiveness: float = 0) -> bool:
    """Record user response to a recommendation."""
    conn = _ensure_db()
    try:
        result = conn.execute("""
            UPDATE recommendations SET accepted=?, feedback=?, effectiveness=?
            WHERE rec_id=?
        """, (int(accepted), feedback, effectiveness, rec_id))
        conn.commit()

        # Learn from the response
        if result.rowcount > 0:
            row = conn.execute(
                "SELECT category, subject, recommendation FROM recommendations WHERE rec_id=?",
                (rec_id,)
            ).fetchone()
            if row:
                action = "accepted" if accepted else "rejected"
                store_memory(
                    category="correction",
                    subject=row[1],
                    key=f"rec_{rec_id}_{action}",
                    value=f"User {action} recommendation: {row[2][:200]}. Feedback: {feedback}",
                    source="user",
                    tags="recommendation,feedback",
                )

        return result.rowcount > 0
    finally:
        conn.close()


def get_recommendations(category: str = "", pending_only: bool = False,
                        limit: int = 20) -> List[Recommendation]:
    """Get recommendations, optionally filtered."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM recommendations WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if pending_only:
            sql += " AND accepted IS NULL"
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM recommendations LIMIT 0").description]
        result = []
        for r in rows:
            d = dict(zip(cols, r))
            if d.get("accepted") is not None:
                d["accepted"] = bool(d["accepted"])
            result.append(Recommendation(**d))
        return result
    finally:
        conn.close()


def get_recommendation_insights() -> Dict[str, Any]:
    """Analyze recommendation acceptance patterns for adaptive learning."""
    conn = _ensure_db()
    try:
        by_category = conn.execute("""
            SELECT category,
                   COUNT(*) as total,
                   SUM(CASE WHEN accepted=1 THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN accepted=0 THEN 1 ELSE 0 END) as rejected,
                   AVG(CASE WHEN accepted=1 THEN effectiveness ELSE NULL END) as avg_effectiveness
            FROM recommendations
            GROUP BY category
        """).fetchall()

        return {
            "by_category": [
                {
                    "category": r[0],
                    "total": r[1],
                    "accepted": r[2] or 0,
                    "rejected": r[3] or 0,
                    "acceptance_rate": round((r[2] or 0) / r[1] * 100, 1) if r[1] > 0 else 0,
                    "avg_effectiveness": round(r[4] or 0, 2),
                }
                for r in by_category
            ],
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Bulk knowledge operations
# -----------------------------------------------------------------------

def export_knowledge(output_path: Optional[str] = None) -> str:
    """Export all memories to a JSON file."""
    conn = _ensure_db()
    try:
        rows = conn.execute("SELECT * FROM memories ORDER BY category, subject, key").fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM memories LIMIT 0").description]
        data = [dict(zip(cols, r)) for r in rows]

        if not output_path:
            output_path = str(TOOLKIT_ROOT / "data" / "knowledge_export.json")

        os.makedirs(Path(output_path).parent, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Exported %d memories to %s", len(data), output_path)
        return output_path
    finally:
        conn.close()


def import_knowledge(input_path: str, overwrite: bool = False) -> Dict[str, int]:
    """Import memories from a JSON file."""
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    imported = 0
    skipped = 0
    for entry in data:
        category = entry.get("category", "")
        subject = entry.get("subject", "")
        key = entry.get("key", "")
        value = entry.get("value", "")
        if not all([category, subject, key, value]):
            skipped += 1
            continue

        if not overwrite:
            existing = recall_memory(category, subject, key)
            if existing:
                skipped += 1
                continue

        store_memory(
            category=category, subject=subject, key=key, value=value,
            confidence=entry.get("confidence", 1.0),
            source=entry.get("source", "import"),
            tags=entry.get("tags", ""),
        )
        imported += 1

    return {"imported": imported, "skipped": skipped, "total": len(data)}


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python agent_memory.py stats       — Memory statistics")
        print("  python agent_memory.py search <q>  — Search memories")
        print("  python agent_memory.py store <cat> <subj> <key> <val>")
        print("  python agent_memory.py export [path]")
        print("  python agent_memory.py import <path>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        stats = get_memory_stats()
        print(json.dumps(stats, indent=2))

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        results = search_memories(q)
        for m in results:
            print(f"  [{m.category}] {m.subject}/{m.key}: {m.value[:80]}")

    elif cmd == "store":
        if len(sys.argv) < 6:
            print("Need: category subject key value")
        else:
            mem = store_memory(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
            print(f"Stored memory #{mem.memory_id}")

    elif cmd == "export":
        path = sys.argv[2] if len(sys.argv) > 2 else None
        result = export_knowledge(path)
        print(f"Exported to: {result}")

    elif cmd == "import":
        path = sys.argv[2] if len(sys.argv) > 2 else ""
        if not path:
            print("Need: input path")
        else:
            result = import_knowledge(path)
            print(f"Imported: {result}")
