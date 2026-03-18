"""
M31 -- Multi-Drive Collection Sync

Provides:
  - Sync collection across multiple drives/locations
  - Conflict resolution for diverged copies (newer wins, larger wins, manual)
  - Bandwidth-efficient delta sync (only copy changed/missing files)
  - Sync scheduling and monitoring
  - Integration with drive_manifest for drive awareness
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("drive_sync")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "drive_sync.db"

# Conflict resolution strategies
STRATEGY_NEWER = "newer"         # Keep the newer file
STRATEGY_LARGER = "larger"       # Keep the larger file
STRATEGY_SOURCE = "source"       # Always prefer source
STRATEGY_DEST = "dest"           # Always prefer destination
STRATEGY_SKIP = "skip"           # Skip conflicts


@dataclass
class SyncPair:
    """A source-destination sync pair."""
    pair_id: int = 0
    name: str = ""
    source_dir: str = ""
    dest_dir: str = ""
    pattern: str = "*"           # glob pattern filter
    recursive: bool = True
    conflict_strategy: str = STRATEGY_NEWER
    delete_orphans: bool = False  # delete dest files not in source
    enabled: bool = True
    last_sync: str = ""
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    pair_name: str = ""
    source_dir: str = ""
    dest_dir: str = ""
    files_scanned: int = 0
    files_copied: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    files_conflicted: int = 0
    files_deleted: int = 0
    bytes_transferred: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mb_transferred"] = round(self.bytes_transferred / (1024 * 1024), 2)
        return d


@dataclass
class SyncDiff:
    """Difference analysis between source and dest."""
    source_only: List[Dict[str, Any]] = field(default_factory=list)
    dest_only: List[Dict[str, Any]] = field(default_factory=list)
    newer_in_source: List[Dict[str, Any]] = field(default_factory=list)
    newer_in_dest: List[Dict[str, Any]] = field(default_factory=list)
    identical: int = 0
    total_source: int = 0
    total_dest: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["source_only_count"] = len(self.source_only)
        d["dest_only_count"] = len(self.dest_only)
        d["newer_source_count"] = len(self.newer_in_source)
        d["newer_dest_count"] = len(self.newer_in_dest)
        # Cap lists for output
        d["source_only"] = self.source_only[:50]
        d["dest_only"] = self.dest_only[:50]
        d["newer_in_source"] = self.newer_in_source[:50]
        d["newer_in_dest"] = self.newer_in_dest[:50]
        return d


# -----------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sync_pairs (
            pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            source_dir TEXT NOT NULL,
            dest_dir TEXT NOT NULL,
            pattern TEXT DEFAULT '*',
            recursive INTEGER DEFAULT 1,
            conflict_strategy TEXT DEFAULT 'newer',
            delete_orphans INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            last_sync TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sync_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            files_copied INTEGER DEFAULT 0,
            files_updated INTEGER DEFAULT 0,
            files_skipped INTEGER DEFAULT 0,
            files_deleted INTEGER DEFAULT 0,
            bytes_transferred INTEGER DEFAULT 0,
            errors_json TEXT DEFAULT '[]',
            duration_seconds REAL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_history_pair ON sync_history(pair_name);
        CREATE INDEX IF NOT EXISTS idx_history_ts ON sync_history(timestamp);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Sync pair management
# -----------------------------------------------------------------------

def create_sync_pair(name: str, source_dir: str, dest_dir: str,
                     pattern: str = "*", recursive: bool = True,
                     conflict_strategy: str = STRATEGY_NEWER,
                     delete_orphans: bool = False) -> SyncPair:
    """Create a new sync pair configuration."""
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("""
            INSERT INTO sync_pairs (name, source_dir, dest_dir, pattern, recursive,
                                    conflict_strategy, delete_orphans, enabled, created_at)
            VALUES (?,?,?,?,?,?,?,1,?)
        """, (name, source_dir, dest_dir, pattern, int(recursive),
              conflict_strategy, int(delete_orphans), now))
        conn.commit()
        return SyncPair(pair_id=cur.lastrowid, name=name, source_dir=source_dir,
                        dest_dir=dest_dir, pattern=pattern, recursive=recursive,
                        conflict_strategy=conflict_strategy,
                        delete_orphans=delete_orphans, enabled=True, created_at=now)
    finally:
        conn.close()


def list_sync_pairs(enabled_only: bool = False) -> List[SyncPair]:
    """List all configured sync pairs."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM sync_pairs"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY name"
        rows = conn.execute(sql).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM sync_pairs LIMIT 0").description]
        pairs = []
        for r in rows:
            d = dict(zip(cols, r))
            d["recursive"] = bool(d["recursive"])
            d["delete_orphans"] = bool(d["delete_orphans"])
            d["enabled"] = bool(d["enabled"])
            pairs.append(SyncPair(**d))
        return pairs
    finally:
        conn.close()


def delete_sync_pair(name: str) -> bool:
    """Delete a sync pair by name."""
    conn = _ensure_db()
    try:
        cur = conn.execute("DELETE FROM sync_pairs WHERE name=?", (name,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# -----------------------------------------------------------------------
# File scanning
# -----------------------------------------------------------------------

def _scan_files(directory: str, pattern: str = "*",
                recursive: bool = True) -> Dict[str, Dict[str, Any]]:
    """Scan directory and return dict of relative_path -> file info."""
    base = Path(directory)
    if not base.exists():
        return {}

    files = {}
    glob_method = base.rglob if recursive else base.glob
    for entry in glob_method(pattern):
        if not entry.is_file():
            continue
        try:
            stat = entry.stat()
            rel = str(entry.relative_to(base))
            files[rel] = {
                "abs_path": str(entry),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        except (OSError, PermissionError):
            continue

    return files


# -----------------------------------------------------------------------
# Diff analysis
# -----------------------------------------------------------------------

def analyze_diff(source_dir: str, dest_dir: str,
                 pattern: str = "*", recursive: bool = True) -> Dict[str, Any]:
    """Analyze differences between source and destination.

    Returns:
        Detailed diff report
    """
    src_files = _scan_files(source_dir, pattern, recursive)
    dst_files = _scan_files(dest_dir, pattern, recursive)

    diff = SyncDiff(total_source=len(src_files), total_dest=len(dst_files))

    src_keys = set(src_files.keys())
    dst_keys = set(dst_files.keys())

    # Source only
    for rel in sorted(src_keys - dst_keys):
        f = src_files[rel]
        diff.source_only.append({"path": rel, "size": f["size"], "modified": f["mtime_iso"]})

    # Dest only
    for rel in sorted(dst_keys - src_keys):
        f = dst_files[rel]
        diff.dest_only.append({"path": rel, "size": f["size"], "modified": f["mtime_iso"]})

    # Common files
    for rel in sorted(src_keys & dst_keys):
        sf = src_files[rel]
        df = dst_files[rel]
        if sf["size"] == df["size"] and abs(sf["mtime"] - df["mtime"]) < 2:
            diff.identical += 1
        elif sf["mtime"] > df["mtime"]:
            diff.newer_in_source.append({
                "path": rel,
                "src_size": sf["size"], "dst_size": df["size"],
                "src_modified": sf["mtime_iso"], "dst_modified": df["mtime_iso"],
            })
        else:
            diff.newer_in_dest.append({
                "path": rel,
                "src_size": sf["size"], "dst_size": df["size"],
                "src_modified": sf["mtime_iso"], "dst_modified": df["mtime_iso"],
            })

    return diff.to_dict()


# -----------------------------------------------------------------------
# Sync execution
# -----------------------------------------------------------------------

def execute_sync(source_dir: str, dest_dir: str,
                 pattern: str = "*", recursive: bool = True,
                 conflict_strategy: str = STRATEGY_NEWER,
                 delete_orphans: bool = False,
                 dry_run: bool = False,
                 pair_name: str = "") -> Dict[str, Any]:
    """Execute a sync operation from source to destination.

    Args:
        source_dir: Source directory
        dest_dir: Destination directory
        pattern: Glob pattern filter
        recursive: Include subdirectories
        conflict_strategy: How to resolve conflicts
        delete_orphans: Remove dest files not in source
        dry_run: Preview only, don't copy
        pair_name: Name for logging

    Returns:
        Sync result report
    """
    import time
    start = time.time()

    result = SyncResult(
        pair_name=pair_name or f"{source_dir} -> {dest_dir}",
        source_dir=source_dir,
        dest_dir=dest_dir,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    src_files = _scan_files(source_dir, pattern, recursive)
    dst_files = _scan_files(dest_dir, pattern, recursive)
    result.files_scanned = len(src_files)

    src_keys = set(src_files.keys())
    dst_keys = set(dst_files.keys())

    # Copy files only in source
    for rel in sorted(src_keys - dst_keys):
        sf = src_files[rel]
        dest_path = Path(dest_dir) / rel
        if not dry_run:
            try:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sf["abs_path"], str(dest_path))
                result.files_copied += 1
                result.bytes_transferred += sf["size"]
            except Exception as e:
                result.errors.append(f"Copy failed {rel}: {e}")
        else:
            result.files_copied += 1
            result.bytes_transferred += sf["size"]

    # Handle common files with conflicts
    for rel in sorted(src_keys & dst_keys):
        sf = src_files[rel]
        df = dst_files[rel]

        if sf["size"] == df["size"] and abs(sf["mtime"] - df["mtime"]) < 2:
            result.files_skipped += 1
            continue

        # Conflict detected
        should_copy = False
        if conflict_strategy == STRATEGY_NEWER:
            should_copy = sf["mtime"] > df["mtime"]
        elif conflict_strategy == STRATEGY_LARGER:
            should_copy = sf["size"] > df["size"]
        elif conflict_strategy == STRATEGY_SOURCE:
            should_copy = True
        elif conflict_strategy == STRATEGY_DEST:
            should_copy = False
        elif conflict_strategy == STRATEGY_SKIP:
            should_copy = False

        if should_copy:
            if not dry_run:
                try:
                    dest_path = Path(dest_dir) / rel
                    shutil.copy2(sf["abs_path"], str(dest_path))
                    result.files_updated += 1
                    result.bytes_transferred += sf["size"]
                except Exception as e:
                    result.errors.append(f"Update failed {rel}: {e}")
            else:
                result.files_updated += 1
                result.bytes_transferred += sf["size"]
        else:
            result.files_conflicted += 1

    # Delete orphans in dest
    if delete_orphans:
        for rel in sorted(dst_keys - src_keys):
            df = dst_files[rel]
            if not dry_run:
                try:
                    os.remove(df["abs_path"])
                    result.files_deleted += 1
                except Exception as e:
                    result.errors.append(f"Delete failed {rel}: {e}")
            else:
                result.files_deleted += 1

    result.duration_seconds = round(time.time() - start, 2)

    # Save history
    if not dry_run and pair_name:
        _save_history(result)

    return result.to_dict()


def sync_pair_by_name(pair_name: str, dry_run: bool = False) -> Dict[str, Any]:
    """Execute sync for a named pair."""
    pairs = list_sync_pairs()
    pair = next((p for p in pairs if p.name == pair_name), None)
    if not pair:
        return {"error": f"Sync pair '{pair_name}' not found"}
    if not pair.enabled:
        return {"error": f"Sync pair '{pair_name}' is disabled"}

    result = execute_sync(
        pair.source_dir, pair.dest_dir, pair.pattern,
        pair.recursive, pair.conflict_strategy,
        pair.delete_orphans, dry_run, pair.name,
    )

    # Update last_sync
    if not dry_run:
        conn = _ensure_db()
        try:
            conn.execute("UPDATE sync_pairs SET last_sync=? WHERE name=?",
                         (datetime.now(timezone.utc).isoformat(), pair_name))
            conn.commit()
        finally:
            conn.close()

    return result


def _save_history(result: SyncResult):
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT INTO sync_history
            (pair_name, timestamp, files_copied, files_updated, files_skipped,
             files_deleted, bytes_transferred, errors_json, duration_seconds)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (result.pair_name, result.timestamp, result.files_copied,
              result.files_updated, result.files_skipped, result.files_deleted,
              result.bytes_transferred, json.dumps(result.errors),
              result.duration_seconds))
        conn.commit()
    finally:
        conn.close()


def get_sync_history(pair_name: str = "", limit: int = 20) -> Dict[str, Any]:
    """Get sync history."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM sync_history"
        params: list = []
        if pair_name:
            sql += " WHERE pair_name=?"
            params.append(pair_name)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM sync_history LIMIT 0").description]
        return {
            "history": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
        }
    finally:
        conn.close()


def sync_status() -> Dict[str, Any]:
    """Get overall sync status."""
    pairs = list_sync_pairs()
    conn = _ensure_db()
    try:
        total_history = conn.execute("SELECT COUNT(*) FROM sync_history").fetchone()[0]
        return {
            "total_pairs": len(pairs),
            "enabled_pairs": sum(1 for p in pairs if p.enabled),
            "pairs": [p.to_dict() for p in pairs],
            "total_syncs_completed": total_history,
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python drive_sync.py diff <source> <dest>")
        print("  python drive_sync.py sync <source> <dest> [--dry-run]")
        print("  python drive_sync.py status")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "diff":
        src = sys.argv[2] if len(sys.argv) > 2 else ""
        dst = sys.argv[3] if len(sys.argv) > 3 else ""
        result = analyze_diff(src, dst)
        print(json.dumps(result, indent=2))

    elif cmd == "sync":
        src = sys.argv[2] if len(sys.argv) > 2 else ""
        dst = sys.argv[3] if len(sys.argv) > 3 else ""
        dry = "--dry-run" in sys.argv
        result = execute_sync(src, dst, dry_run=dry)
        print(json.dumps(result, indent=2))

    elif cmd == "status":
        result = sync_status()
        print(json.dumps(result, indent=2))
