"""M14 — Pre/Post Update Snapshot Verification.

Creates file-level snapshots before updates and verifies integrity after:
  - Capture snapshot: file list, sizes, hashes, permissions
  - Compare pre vs post snapshots to detect drift
  - Verify expected changes vs unexpected changes
  - Generate verification reports
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("snapshot_verify")

# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------
_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    target_path TEXT NOT NULL,
    snapshot_type TEXT DEFAULT 'pre',     -- pre, post, manual
    file_count INTEGER DEFAULT 0,
    total_size_bytes INTEGER DEFAULT 0,
    manifest_path TEXT,
    status TEXT DEFAULT 'created',        -- created, verified, failed, stale
    related_update_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    verified_at TEXT,
    notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_snapshots_name ON snapshots(name);
CREATE INDEX IF NOT EXISTS idx_snapshots_update ON snapshots(related_update_id);
"""


def ensure_tables():
    """Run migration to ensure snapshot tables exist."""
    try:
        with db.get_conn() as conn:
            conn.executescript(_MIGRATION_SQL)
        log.debug("M14 tables ensured")
    except Exception as exc:
        log.warning("M14 table migration: %s", exc)


# ---------------------------------------------------------------------------
# Snapshot data structures
# ---------------------------------------------------------------------------

@dataclass
class FileEntry:
    """A single file in a snapshot."""
    path: str
    relative_path: str
    size_bytes: int
    modified: float
    sha256: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "modified": self.modified,
            "sha256": self.sha256,
        }


@dataclass
class Snapshot:
    """A directory snapshot."""
    name: str
    target_path: str
    snapshot_type: str  # pre, post, manual
    files: list[FileEntry] = field(default_factory=list)
    created_at: str = ""
    db_id: int = 0

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_size(self) -> int:
        return sum(f.size_bytes for f in self.files)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target_path": self.target_path,
            "snapshot_type": self.snapshot_type,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size,
            "created_at": self.created_at,
            "db_id": self.db_id,
        }


@dataclass
class DiffResult:
    """Result of comparing two snapshots."""
    pre_snapshot: str
    post_snapshot: str
    added: list[dict] = field(default_factory=list)
    removed: list[dict] = field(default_factory=list)
    modified: list[dict] = field(default_factory=list)
    unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def change_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)

    def to_dict(self) -> dict:
        return {
            "pre_snapshot": self.pre_snapshot,
            "post_snapshot": self.post_snapshot,
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "unchanged": self.unchanged,
            "has_changes": self.has_changes,
            "change_count": self.change_count,
            "summary": {
                "added": len(self.added),
                "removed": len(self.removed),
                "modified": len(self.modified),
                "unchanged": self.unchanged,
            },
        }


# ---------------------------------------------------------------------------
# Core snapshot operations
# ---------------------------------------------------------------------------

def _hash_file(filepath: Path, algo: str = "sha256") -> str:
    """Compute hash of a file."""
    h = hashlib.new(algo)
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as exc:
        log.debug("Cannot hash %s: %s", filepath, exc)
        return ""


def capture_snapshot(target_path: str, name: str | None = None,
                     snapshot_type: str = "manual",
                     compute_hashes: bool = True,
                     related_update_id: int | None = None) -> Snapshot:
    """Capture a snapshot of a directory.

    Args:
        target_path: Directory to snapshot.
        name: Snapshot name (auto-generated if not provided).
        snapshot_type: 'pre', 'post', or 'manual'.
        compute_hashes: Whether to compute SHA256 hashes (slower but more reliable).
        related_update_id: Optional update_history ID to link this snapshot to.

    Returns:
        Snapshot object with all file entries.
    """
    ensure_tables()
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"Target path not found: {target_path}")

    now = datetime.now(timezone.utc).isoformat()
    if not name:
        name = f"{target.name}_{snapshot_type}_{int(time.time())}"

    files: list[FileEntry] = []
    for f in sorted(target.rglob("*")):
        if f.is_file():
            try:
                stat = f.stat()
                entry = FileEntry(
                    path=str(f),
                    relative_path=str(f.relative_to(target)),
                    size_bytes=stat.st_size,
                    modified=stat.st_mtime,
                    sha256=_hash_file(f) if compute_hashes else "",
                )
                files.append(entry)
            except (OSError, PermissionError) as exc:
                log.debug("Skipping %s: %s", f, exc)

    snapshot = Snapshot(
        name=name,
        target_path=str(target),
        snapshot_type=snapshot_type,
        files=files,
        created_at=now,
    )

    # Save manifest to disk
    manifest_dir = Path(cfg_get("paths.output_root", "output")) / "snapshots"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{name}.json"
    manifest_data = {
        "name": name,
        "target_path": str(target),
        "snapshot_type": snapshot_type,
        "created_at": now,
        "file_count": snapshot.file_count,
        "total_size_bytes": snapshot.total_size,
        "files": [fe.to_dict() for fe in files],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # Record in DB
    try:
        db_id = db.insert("snapshots", {
            "name": name,
            "target_path": str(target),
            "snapshot_type": snapshot_type,
            "file_count": snapshot.file_count,
            "total_size_bytes": snapshot.total_size,
            "manifest_path": str(manifest_path),
            "status": "created",
            "related_update_id": related_update_id,
            "notes": "",
        })
        snapshot.db_id = db_id
    except Exception as exc:
        log.warning("DB insert for snapshot %s: %s", name, exc)

    log.info("Snapshot '%s': %d files, %s bytes", name, snapshot.file_count, f"{snapshot.total_size:,}")
    audit("snapshot_created", name, {
        "type": snapshot_type, "files": snapshot.file_count,
        "size": snapshot.total_size, "path": str(target),
    })
    return snapshot


def load_snapshot(name: str) -> Snapshot | None:
    """Load a snapshot from its manifest file."""
    ensure_tables()
    rows = db.execute("SELECT * FROM snapshots WHERE name = ?", (name,))
    if not rows:
        return None

    row = rows[0]
    manifest_path = Path(row.get("manifest_path", ""))
    if not manifest_path.exists():
        return None

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = [
        FileEntry(
            path=f["path"],
            relative_path=f["relative_path"],
            size_bytes=f["size_bytes"],
            modified=f["modified"],
            sha256=f.get("sha256", ""),
        )
        for f in data.get("files", [])
    ]

    return Snapshot(
        name=data["name"],
        target_path=data["target_path"],
        snapshot_type=data["snapshot_type"],
        files=files,
        created_at=data["created_at"],
        db_id=row["id"],
    )


# ---------------------------------------------------------------------------
# Comparison / verification
# ---------------------------------------------------------------------------

def compare_snapshots(pre_name: str, post_name: str) -> DiffResult:
    """Compare two snapshots and return the differences.

    Args:
        pre_name: Name of the pre-update snapshot.
        post_name: Name of the post-update snapshot.

    Returns:
        DiffResult with added, removed, modified, and unchanged counts.
    """
    pre = load_snapshot(pre_name)
    post = load_snapshot(post_name)

    if not pre:
        raise ValueError(f"Pre-snapshot not found: {pre_name}")
    if not post:
        raise ValueError(f"Post-snapshot not found: {post_name}")

    pre_map = {f.relative_path: f for f in pre.files}
    post_map = {f.relative_path: f for f in post.files}

    result = DiffResult(pre_snapshot=pre_name, post_snapshot=post_name)

    # Find added files
    for rp, f in post_map.items():
        if rp not in pre_map:
            result.added.append(f.to_dict())

    # Find removed files
    for rp, f in pre_map.items():
        if rp not in post_map:
            result.removed.append(f.to_dict())

    # Find modified and unchanged
    for rp in pre_map:
        if rp in post_map:
            pre_f = pre_map[rp]
            post_f = post_map[rp]
            changed = False

            if pre_f.sha256 and post_f.sha256:
                changed = pre_f.sha256 != post_f.sha256
            elif pre_f.size_bytes != post_f.size_bytes:
                changed = True
            elif pre_f.modified != post_f.modified:
                changed = True

            if changed:
                result.modified.append({
                    "relative_path": rp,
                    "pre_size": pre_f.size_bytes,
                    "post_size": post_f.size_bytes,
                    "pre_sha256": pre_f.sha256[:12] if pre_f.sha256 else "",
                    "post_sha256": post_f.sha256[:12] if post_f.sha256 else "",
                    "size_delta": post_f.size_bytes - pre_f.size_bytes,
                })
            else:
                result.unchanged += 1

    return result


def verify_update(target_path: str, pre_name: str,
                  expected_changes: list[str] | None = None) -> dict:
    """Verify an update by capturing a post-snapshot and comparing with the pre-snapshot.

    Args:
        target_path: Directory that was updated.
        pre_name: Name of the pre-update snapshot.
        expected_changes: Optional list of relative paths expected to change.

    Returns:
        Verification report dict.
    """
    post_name = f"{pre_name}_post"
    capture_snapshot(target_path, name=post_name, snapshot_type="post")
    diff = compare_snapshots(pre_name, post_name)

    # Classify changes
    unexpected = []
    expected_found = []
    if expected_changes:
        expected_set = set(expected_changes)
        all_changed = set()
        for f in diff.added:
            all_changed.add(f["relative_path"])
        for f in diff.removed:
            all_changed.add(f["relative_path"])
        for f in diff.modified:
            all_changed.add(f["relative_path"])

        expected_found = list(expected_set & all_changed)
        unexpected = list(all_changed - expected_set)

    # Update DB status
    status = "verified" if not unexpected else "failed"
    try:
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE snapshots SET status = ?, verified_at = datetime('now') WHERE name = ?",
                (status, pre_name),
            )
            conn.execute(
                "UPDATE snapshots SET status = ?, verified_at = datetime('now') WHERE name = ?",
                (status, post_name),
            )
    except Exception as exc:
        log.warning("DB update for verification: %s", exc)

    report = {
        "pre_snapshot": pre_name,
        "post_snapshot": post_name,
        "status": status,
        "diff": diff.to_dict(),
        "expected_found": expected_found,
        "unexpected_changes": unexpected,
        "verification_passed": len(unexpected) == 0,
    }

    audit("snapshot_verified", pre_name, {
        "status": status, "changes": diff.change_count,
        "unexpected": len(unexpected),
    })
    return report


# ---------------------------------------------------------------------------
# Listing / querying
# ---------------------------------------------------------------------------

def list_snapshots(target_path: str | None = None,
                   snapshot_type: str | None = None,
                   limit: int = 50) -> list[dict]:
    """List snapshots from the DB with optional filters."""
    ensure_tables()
    sql = "SELECT * FROM snapshots WHERE 1=1"
    params: list = []
    if target_path:
        sql += " AND target_path = ?"
        params.append(target_path)
    if snapshot_type:
        sql += " AND snapshot_type = ?"
        params.append(snapshot_type)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, tuple(params))


def get_snapshot_detail(name: str) -> dict | None:
    """Get full snapshot detail including file list."""
    snap = load_snapshot(name)
    if not snap:
        return None
    return {
        **snap.to_dict(),
        "files": [f.to_dict() for f in snap.files],
    }


def snapshot_summary() -> dict:
    """Get snapshot system summary."""
    ensure_tables()
    total = db.execute("SELECT COUNT(*) as cnt FROM snapshots")
    by_type = db.execute(
        "SELECT snapshot_type, COUNT(*) as cnt FROM snapshots GROUP BY snapshot_type"
    )
    by_status = db.execute(
        "SELECT status, COUNT(*) as cnt FROM snapshots GROUP BY status"
    )
    recent = db.execute(
        "SELECT name, target_path, snapshot_type, status, file_count, created_at "
        "FROM snapshots ORDER BY created_at DESC LIMIT 10"
    )
    return {
        "total_snapshots": total[0]["cnt"] if total else 0,
        "by_type": {r["snapshot_type"]: r["cnt"] for r in by_type},
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "recent": recent,
    }
