"""M12 — Emulator Version Tracker & Updater.

Persistent version tracking for all emulators:
  - Scan emulator directories, detect installed versions, persist to DB
  - Track version history over time (emulator_versions table)
  - Quarantine staging: download updates to quarantine before applying
  - Auto-backup previous version before update
  - Version comparison with semver-like logic
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("version_tracker")

# ---------------------------------------------------------------------------
# Schema migration — add emulator_versions table if missing
# ---------------------------------------------------------------------------
_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS emulator_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emulator_name TEXT NOT NULL,
    version TEXT NOT NULL,
    source TEXT DEFAULT 'scan',          -- scan, update, manual
    exe_path TEXT,
    exe_size_bytes INTEGER DEFAULT 0,
    exe_modified TEXT,
    detected_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_emu_versions_name ON emulator_versions(emulator_name);

CREATE TABLE IF NOT EXISTS quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emulator_name TEXT NOT NULL,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    source_url TEXT,
    release_tag TEXT,
    sha256 TEXT,
    status TEXT DEFAULT 'staged',        -- staged, verified, applied, rejected
    staged_at TEXT NOT NULL DEFAULT (datetime('now')),
    applied_at TEXT,
    notes TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_quarantine_name ON quarantine(emulator_name);
"""


def ensure_tables():
    """Run migration to ensure version tracking tables exist."""
    try:
        with db.get_conn() as conn:
            conn.executescript(_MIGRATION_SQL)
        log.debug("M12 tables ensured")
    except Exception as exc:
        log.warning("M12 table migration: %s", exc)


# ---------------------------------------------------------------------------
# Version parsing & comparison
# ---------------------------------------------------------------------------

def _parse_version(v: str) -> tuple:
    """Parse a version string into a comparable tuple of ints.

    Handles: '0.268', '1.17.0', 'v2.3', 'mame0268', '0268'
    """
    if not v or v == "unknown":
        return (0,)
    # Strip leading v/V
    v = re.sub(r"^[vV]", "", v.strip())
    # Strip common prefixes like 'mame'
    v = re.sub(r"^[a-zA-Z]+", "", v)
    # Remove trailing descriptors like '-beta', ' (modified ...)'
    v = re.split(r"[\s\-(]", v)[0]
    # Extract numeric parts
    parts = re.findall(r"\d+", v)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts)


def version_compare(local: str, remote: str) -> int:
    """Compare two version strings.

    Returns:
        -1 if local < remote (update available)
         0 if equal
         1 if local > remote
    """
    lp = _parse_version(local)
    rp = _parse_version(remote)
    if lp < rp:
        return -1
    elif lp > rp:
        return 1
    return 0


def is_update_available(local_version: str, remote_tag: str) -> bool:
    """Determine if an update is available based on version comparison."""
    if not local_version or local_version == "unknown" or "unknown" in str(local_version):
        return True  # Can't confirm current version, flag for review
    if not remote_tag:
        return False
    return version_compare(local_version, remote_tag) < 0


# ---------------------------------------------------------------------------
# Emulator scanning & version detection
# ---------------------------------------------------------------------------

def scan_emulator_versions(emu_root: str | None = None) -> list[dict[str, Any]]:
    """Scan all emulator directories, detect versions, persist to DB.

    Returns list of emulator version records.
    """
    ensure_tables()
    from engines.emulator_health import check_emulator, KNOWN_EMULATORS

    emu_path = Path(emu_root or cfg_get("paths.emulators_root", ""))
    if not emu_path.exists():
        return [{"error": f"Emulators root not found: {emu_path}"}]

    results = []
    now = datetime.now(timezone.utc).isoformat()

    for entry in sorted(emu_path.iterdir()):
        if not entry.is_dir():
            continue

        health = check_emulator(entry)
        record = {
            "name": entry.name,
            "path": str(entry),
            "exe_path": health.exe_path,
            "exe_exists": health.exe_exists,
            "exe_size_bytes": health.exe_size_bytes,
            "version": health.version,
            "is_healthy": health.is_healthy,
            "health_score": health.health_score,
        }

        # Upsert into emulators table
        try:
            existing = db.execute(
                "SELECT id, version FROM emulators WHERE name = ?", (entry.name,)
            )
            if existing:
                old_ver = existing[0].get("version", "unknown")
                db.execute(
                    """UPDATE emulators SET version = ?, exe_path = ?, is_healthy = ?,
                       last_check = ?, updated_at = ? WHERE name = ?""",
                    (health.version, health.exe_path, int(health.is_healthy), now, now, entry.name),
                )
                # Record version change in history
                if old_ver != health.version and health.version != "unknown":
                    _record_version(entry.name, health.version, "scan",
                                    health.exe_path, health.exe_size_bytes)
                    record["version_changed"] = True
                    record["old_version"] = old_ver
            else:
                db.insert("emulators", {
                    "name": entry.name,
                    "folder_name": entry.name,
                    "exe_path": health.exe_path,
                    "version": health.version,
                    "last_known_version": health.version,
                    "is_healthy": int(health.is_healthy),
                    "last_check": now,
                })
                if health.version != "unknown":
                    _record_version(entry.name, health.version, "scan",
                                    health.exe_path, health.exe_size_bytes)
        except Exception as exc:
            log.warning("DB upsert for %s: %s", entry.name, exc)

        results.append(record)

    log.info("Scanned %d emulators for version tracking", len(results))
    audit("version_scan", f"Scanned {len(results)} emulators")
    return results


def _record_version(emu_name: str, version: str, source: str,
                    exe_path: str = "", exe_size: int = 0, notes: str = ""):
    """Insert a version history record."""
    try:
        db.insert("emulator_versions", {
            "emulator_name": emu_name,
            "version": version,
            "source": source,
            "exe_path": exe_path,
            "exe_size_bytes": exe_size,
            "notes": notes,
        })
    except Exception as exc:
        log.warning("Failed to record version for %s: %s", emu_name, exc)


def get_version_history(emulator_name: str, limit: int = 20) -> list[dict]:
    """Get version history for an emulator."""
    ensure_tables()
    return db.execute(
        "SELECT * FROM emulator_versions WHERE emulator_name = ? ORDER BY detected_at DESC LIMIT ?",
        (emulator_name, limit),
    )


def get_all_tracked(include_versions: bool = False) -> list[dict]:
    """Get all tracked emulators from the DB with optional version history."""
    ensure_tables()
    emulators = db.execute("SELECT * FROM emulators ORDER BY name")
    if include_versions:
        for emu in emulators:
            emu["version_history"] = get_version_history(emu["name"], limit=5)
    return emulators


def get_outdated(emu_root: str | None = None) -> list[dict]:
    """Check all tracked emulators against GitHub releases, return those with updates."""
    from engines.release_checker import EMULATOR_REPOS, fetch_latest_release, detect_local_version
    import time

    ensure_tables()
    outdated = []

    for name, info in EMULATOR_REPOS.items():
        local_ver = detect_local_version(name)
        release = fetch_latest_release(info["owner"], info["repo"])
        time.sleep(1)  # Rate limit

        if not release:
            continue

        remote_tag = re.sub(r"^v", "", release.get("tag", ""))
        if is_update_available(str(local_ver), remote_tag):
            outdated.append({
                "emulator": name,
                "local_version": local_ver,
                "remote_version": remote_tag,
                "release_tag": release["tag"],
                "release_name": release.get("name", ""),
                "published": release.get("published", ""),
                "release_url": release.get("url", ""),
                "assets_count": len(release.get("assets", [])),
            })

    return {"outdated": outdated, "count": len(outdated),
            "total_tracked": len(EMULATOR_REPOS)}


# ---------------------------------------------------------------------------
# Quarantine staging
# ---------------------------------------------------------------------------

def _quarantine_dir() -> Path:
    """Get or create the quarantine directory."""
    qdir = Path(cfg_get("paths.output_root", "output")) / "quarantine"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir


def stage_update(emulator_name: str, target_dir: str | None = None) -> dict:
    """Download the latest release to quarantine staging area.

    Does NOT apply the update — only downloads and records in quarantine DB.
    """
    ensure_tables()
    from engines.release_checker import check_single_emulator, find_matching_asset, EMULATOR_REPOS
    import httpx

    info = EMULATOR_REPOS.get(emulator_name)
    if not info:
        return {"error": f"Unknown emulator: {emulator_name}"}

    release_info = check_single_emulator(emulator_name)
    if not release_info or not release_info.get("download_url"):
        return {"error": f"No download URL found for {emulator_name}"}

    qdir = Path(target_dir) if target_dir else _quarantine_dir() / emulator_name
    qdir.mkdir(parents=True, exist_ok=True)

    url = release_info["download_url"]
    filename = url.split("/")[-1]
    filepath = qdir / filename

    if filepath.exists():
        return {
            "emulator": emulator_name,
            "status": "already_staged",
            "filepath": str(filepath),
            "size_bytes": filepath.stat().st_size,
            "release_tag": release_info.get("latest_tag"),
        }

    log.info("Staging %s to quarantine: %s", emulator_name, filepath)
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
    except Exception as exc:
        if filepath.exists():
            filepath.unlink()
        return {"error": f"Download failed: {exc}"}

    size = filepath.stat().st_size

    # Compute SHA256
    import hashlib
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    sha256 = sha.hexdigest()

    # Record in quarantine DB
    qid = db.insert("quarantine", {
        "emulator_name": emulator_name,
        "filename": filename,
        "filepath": str(filepath),
        "size_bytes": size,
        "source_url": url,
        "release_tag": release_info.get("latest_tag", ""),
        "sha256": sha256,
        "status": "staged",
    })

    audit("update_staged", f"{emulator_name}: {filename} ({size} bytes)")
    return {
        "emulator": emulator_name,
        "quarantine_id": qid,
        "status": "staged",
        "filepath": str(filepath),
        "filename": filename,
        "size_bytes": size,
        "sha256": sha256,
        "release_tag": release_info.get("latest_tag"),
    }


def list_quarantine(emulator_name: str | None = None) -> list[dict]:
    """List all quarantined (staged) updates."""
    ensure_tables()
    if emulator_name:
        return db.execute(
            "SELECT * FROM quarantine WHERE emulator_name = ? ORDER BY staged_at DESC",
            (emulator_name,),
        )
    return db.execute("SELECT * FROM quarantine ORDER BY staged_at DESC")


def reject_quarantine(quarantine_id: int) -> dict:
    """Reject and delete a quarantined update."""
    ensure_tables()
    rows = db.execute("SELECT * FROM quarantine WHERE id = ?", (quarantine_id,))
    if not rows:
        return {"error": f"Quarantine entry {quarantine_id} not found"}
    entry = rows[0]
    fp = Path(entry["filepath"])
    if fp.exists():
        fp.unlink()
    with db.get_conn() as conn:
        conn.execute("UPDATE quarantine SET status = 'rejected' WHERE id = ?", (quarantine_id,))
    return {"rejected": True, "quarantine_id": quarantine_id, "emulator": entry["emulator_name"]}


# ---------------------------------------------------------------------------
# Apply from quarantine (with auto-backup)
# ---------------------------------------------------------------------------

def apply_staged_update(quarantine_id: int, test_cmd: str | None = None,
                        dry_run: bool = False) -> dict:
    """Apply a quarantined update with automatic pre-update backup.

    Workflow: verify staged file → backup current → apply → test → commit/rollback.
    """
    ensure_tables()
    rows = db.execute("SELECT * FROM quarantine WHERE id = ?", (quarantine_id,))
    if not rows:
        return {"error": f"Quarantine entry {quarantine_id} not found"}
    entry = rows[0]

    if entry["status"] != "staged":
        return {"error": f"Quarantine entry {quarantine_id} status is '{entry['status']}', expected 'staged'"}

    emu_name = entry["emulator_name"]
    staged_file = entry["filepath"]

    if not Path(staged_file).exists():
        return {"error": f"Staged file missing: {staged_file}"}

    # Verify SHA256
    import hashlib
    sha = hashlib.sha256()
    with open(staged_file, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    if sha.hexdigest() != entry.get("sha256"):
        with db.get_conn() as conn:
            conn.execute("UPDATE quarantine SET status = 'rejected', notes = 'SHA256 mismatch' WHERE id = ?",
                         (quarantine_id,))
        return {"error": "SHA256 verification failed — file may be corrupted"}

    # Mark as verified
    with db.get_conn() as conn:
        conn.execute("UPDATE quarantine SET status = 'verified' WHERE id = ?", (quarantine_id,))

    # Delegate to update_applier for the actual apply pipeline
    from engines.update_applier import apply_update
    result = apply_update(emu_name, staged_file, test_cmd=test_cmd, dry_run=dry_run)

    # Update quarantine status
    final_status = "applied" if result.get("status") in ("committed", "dry_run") else "rejected"
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE quarantine SET status = ?, applied_at = datetime('now'), notes = ? WHERE id = ?",
            (final_status, json.dumps(result.get("steps", []), default=str), quarantine_id),
        )

    # Record version change
    if result.get("new_version") and result.get("status") == "committed":
        _record_version(emu_name, result["new_version"], "update",
                        notes=f"from quarantine #{quarantine_id}")

    result["quarantine_id"] = quarantine_id
    return result


# ---------------------------------------------------------------------------
# Summary / dashboard data
# ---------------------------------------------------------------------------

def tracker_summary() -> dict:
    """Get a summary of the version tracking state."""
    ensure_tables()
    emulators = db.execute("SELECT COUNT(*) as cnt FROM emulators")
    versions = db.execute("SELECT COUNT(*) as cnt FROM emulator_versions")
    quarantined = db.execute("SELECT COUNT(*) as cnt FROM quarantine WHERE status = 'staged'")
    recent_changes = db.execute(
        "SELECT * FROM emulator_versions ORDER BY detected_at DESC LIMIT 10"
    )
    return {
        "tracked_emulators": emulators[0]["cnt"] if emulators else 0,
        "total_version_records": versions[0]["cnt"] if versions else 0,
        "quarantined_updates": quarantined[0]["cnt"] if quarantined else 0,
        "recent_changes": recent_changes,
    }
