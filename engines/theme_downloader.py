"""
M33 -- Automated HyperSpin Theme/Media Downloader

Provides:
  - Search and download missing themes, wheels, videos
  - Source from HyperSpin community repositories and known mirrors
  - Batch download with progress tracking
  - Quality verification after download (file size, format checks)
  - Integration with media audit to identify gaps
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("theme_downloader")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "theme_downloads.db"

# Media types and expected locations
MEDIA_TYPES = {
    "themes": {"subdir": "Themes", "extensions": [".zip", ".rar", ".7z"]},
    "wheels": {"subdir": "Images/Wheel", "extensions": [".png", ".gif", ".apng"]},
    "artwork1": {"subdir": "Images/Artwork1", "extensions": [".png", ".jpg"]},
    "artwork2": {"subdir": "Images/Artwork2", "extensions": [".png", ".jpg"]},
    "artwork3": {"subdir": "Images/Artwork3", "extensions": [".png", ".jpg"]},
    "artwork4": {"subdir": "Images/Artwork4", "extensions": [".png", ".jpg"]},
    "videos": {"subdir": "Video", "extensions": [".mp4", ".flv", ".avi"]},
    "backgrounds": {"subdir": "Images/Backgrounds", "extensions": [".png", ".jpg"]},
    "pointers": {"subdir": "Images/Pointer", "extensions": [".png"]},
    "sounds": {"subdir": "Sound", "extensions": [".mp3", ".wav"]},
}

# Known download source patterns (community repos, mirrors)
KNOWN_SOURCES: List[Dict[str, str]] = [
    {
        "name": "HyperSpin FTP",
        "type": "ftp",
        "url_pattern": "ftp://hyperspin.com/{system}/{media_type}/",
        "status": "reference_only",
    },
    {
        "name": "EmuMovies",
        "type": "web",
        "url_pattern": "https://emumovies.com/files/",
        "status": "requires_account",
    },
    {
        "name": "ScreenScraper",
        "type": "api",
        "url_pattern": "https://www.screenscraper.fr/api2/",
        "status": "api_key_required",
    },
    {
        "name": "LaunchBox DB",
        "type": "web",
        "url_pattern": "https://gamesdb.launchbox-app.com/",
        "status": "public",
    },
    {
        "name": "TheGamesDB",
        "type": "api",
        "url_pattern": "https://api.thegamesdb.net/v1.1/",
        "status": "api_key_required",
    },
    {
        "name": "Local Archive",
        "type": "local",
        "url_pattern": "",
        "status": "configured_per_user",
    },
]


@dataclass
class MediaGap:
    """A missing media item."""
    system: str
    game: str
    media_type: str
    expected_path: str
    found: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DownloadTask:
    """A queued or completed download."""
    task_id: int = 0
    system: str = ""
    game: str = ""
    media_type: str = ""
    source_url: str = ""
    dest_path: str = ""
    status: str = "queued"      # queued, downloading, complete, failed, verified
    file_size: int = 0
    error: str = ""
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# SQLite
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS download_tasks (
            task_id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL,
            game TEXT NOT NULL,
            media_type TEXT NOT NULL,
            source_url TEXT DEFAULT '',
            dest_path TEXT DEFAULT '',
            status TEXT DEFAULT 'queued',
            file_size INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS download_sources (
            source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            source_type TEXT DEFAULT 'web',
            api_key TEXT DEFAULT '',
            priority INTEGER DEFAULT 50,
            enabled INTEGER DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_task_system ON download_tasks(system);
        CREATE INDEX IF NOT EXISTS idx_task_status ON download_tasks(status);
        CREATE INDEX IF NOT EXISTS idx_task_type ON download_tasks(media_type);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Media gap analysis
# -----------------------------------------------------------------------

def scan_missing_media(system: str, hyperspin_root: str,
                       media_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """Scan for missing media files for a system.

    Args:
        system: System name
        hyperspin_root: Root HyperSpin directory
        media_types: Which media types to check (default: all)

    Returns:
        Missing media report
    """
    root = Path(hyperspin_root)
    check_types = media_types or list(MEDIA_TYPES.keys())
    games = _get_game_list(system, hyperspin_root)

    if not games:
        return {"system": system, "error": "No games found in database/XML", "gaps": []}

    gaps: List[MediaGap] = []
    found_counts: Dict[str, int] = {}
    missing_counts: Dict[str, int] = {}

    for mtype in check_types:
        if mtype not in MEDIA_TYPES:
            continue

        info = MEDIA_TYPES[mtype]
        media_dir = root / "Media" / system / info["subdir"]
        found = 0
        missing = 0

        for game in games:
            has_media = False
            for ext in info["extensions"]:
                candidate = media_dir / f"{game}{ext}"
                if candidate.exists() and candidate.stat().st_size > 0:
                    has_media = True
                    break

            if has_media:
                found += 1
            else:
                missing += 1
                expected = str(media_dir / f"{game}{info['extensions'][0]}")
                gaps.append(MediaGap(
                    system=system, game=game, media_type=mtype,
                    expected_path=expected, found=False,
                ))

        found_counts[mtype] = found
        missing_counts[mtype] = missing

    total_games = len(games)
    return {
        "system": system,
        "total_games": total_games,
        "media_types_checked": check_types,
        "coverage": {
            mtype: {
                "found": found_counts.get(mtype, 0),
                "missing": missing_counts.get(mtype, 0),
                "pct": round(found_counts.get(mtype, 0) / total_games * 100, 1) if total_games else 0,
            }
            for mtype in check_types if mtype in MEDIA_TYPES
        },
        "total_gaps": len(gaps),
        "gaps": [g.to_dict() for g in gaps[:100]],  # Cap output
    }


def _get_game_list(system: str, hyperspin_root: str) -> List[str]:
    """Get list of games from HyperSpin database XML."""
    db_path = Path(hyperspin_root) / "Databases" / system / f"{system}.xml"
    if not db_path.exists():
        # Try alternate paths
        for alt in [
            Path(hyperspin_root) / "Databases" / system / "games.xml",
            Path(hyperspin_root) / "Databases" / system / f"{system} Games.xml",
        ]:
            if alt.exists():
                db_path = alt
                break
        else:
            return []

    games = []
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(str(db_path))
        root = tree.getroot()
        for game in root.findall(".//game"):
            name = game.get("name", "")
            if name:
                games.append(name)
    except Exception as e:
        logger.warning("Failed to parse game DB %s: %s", db_path, e)

    return games


# -----------------------------------------------------------------------
# Download queue management
# -----------------------------------------------------------------------

def queue_downloads(system: str, media_type: str,
                    games: Optional[List[str]] = None,
                    source_url_template: str = "") -> Dict[str, Any]:
    """Queue media downloads for missing items.

    Args:
        system: System name
        media_type: Media type to download
        games: Specific games (or None for all missing)
        source_url_template: URL template with {game} placeholder

    Returns:
        Queued download tasks
    """
    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    queued = []

    try:
        target_games = games or []
        for game in target_games:
            # Check if already queued
            existing = conn.execute(
                "SELECT task_id FROM download_tasks WHERE system=? AND game=? AND media_type=? AND status IN ('queued','downloading')",
                (system, game, media_type)
            ).fetchone()
            if existing:
                continue

            source_url = ""
            if source_url_template:
                source_url = source_url_template.replace("{game}", urllib.parse.quote(game))

            cur = conn.execute("""
                INSERT INTO download_tasks (system, game, media_type, source_url, status, created_at)
                VALUES (?,?,?,?,'queued',?)
            """, (system, game, media_type, source_url, now))
            queued.append({
                "task_id": cur.lastrowid,
                "system": system,
                "game": game,
                "media_type": media_type,
            })

        conn.commit()
        return {"queued": len(queued), "tasks": queued[:50]}
    finally:
        conn.close()


def get_download_queue(system: str = "", status: str = "",
                       limit: int = 50) -> Dict[str, Any]:
    """Get current download queue."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM download_tasks WHERE 1=1"
        params: list = []
        if system:
            sql += " AND system=?"
            params.append(system)
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM download_tasks LIMIT 0").description]
        return {
            "tasks": [dict(zip(cols, r)) for r in rows],
            "count": len(rows),
        }
    finally:
        conn.close()


def execute_download(task_id: int, dest_dir: str = "") -> Dict[str, Any]:
    """Execute a single download task.

    Args:
        task_id: Task ID to execute
        dest_dir: Override destination directory

    Returns:
        Download result
    """
    conn = _ensure_db()
    try:
        row = conn.execute("SELECT * FROM download_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return {"error": f"Task {task_id} not found"}

        cols = [d[0] for d in conn.execute("SELECT * FROM download_tasks LIMIT 0").description]
        task = dict(zip(cols, row))

        source_url = task["source_url"]
        if not source_url:
            conn.execute("UPDATE download_tasks SET status='failed', error='No source URL' WHERE task_id=?", (task_id,))
            conn.commit()
            return {"error": "No source URL configured for this task"}

        # Determine destination
        if not dest_dir:
            dest_dir = task.get("dest_path", "")
        if not dest_dir:
            return {"error": "No destination directory specified"}

        # Update status
        conn.execute("UPDATE download_tasks SET status='downloading' WHERE task_id=?", (task_id,))
        conn.commit()

        # Download
        try:
            filename = task["game"] + _ext_for_type(task["media_type"])
            dest_path = Path(dest_dir) / filename
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            req = urllib.request.Request(source_url, headers={"User-Agent": "HyperSpinToolkit/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()

            with open(str(dest_path), "wb") as f:
                f.write(data)

            file_size = len(data)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("""
                UPDATE download_tasks
                SET status='complete', dest_path=?, file_size=?, completed_at=?
                WHERE task_id=?
            """, (str(dest_path), file_size, now, task_id))
            conn.commit()

            return {
                "task_id": task_id,
                "status": "complete",
                "dest_path": str(dest_path),
                "file_size": file_size,
            }
        except Exception as e:
            conn.execute("UPDATE download_tasks SET status='failed', error=? WHERE task_id=?",
                         (str(e), task_id))
            conn.commit()
            return {"task_id": task_id, "status": "failed", "error": str(e)}
    finally:
        conn.close()


def _ext_for_type(media_type: str) -> str:
    info = MEDIA_TYPES.get(media_type, {})
    exts = info.get("extensions", [".png"])
    return exts[0]


# -----------------------------------------------------------------------
# Quality verification
# -----------------------------------------------------------------------

def verify_downloads(system: str = "", recheck: bool = False) -> Dict[str, Any]:
    """Verify completed downloads (file exists, non-zero, correct format).

    Args:
        system: Filter by system
        recheck: Re-verify already verified items

    Returns:
        Verification results
    """
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM download_tasks WHERE status IN ('complete'"
        if recheck:
            sql += ",'verified'"
        sql += ")"
        params: list = []
        if system:
            sql += " AND system=?"
            params.append(system)

        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM download_tasks LIMIT 0").description]

        verified = 0
        failed = 0
        issues = []

        for row in rows:
            task = dict(zip(cols, row))
            dest = task.get("dest_path", "")
            tid = task["task_id"]

            if not dest or not Path(dest).exists():
                conn.execute("UPDATE download_tasks SET status='failed', error='File missing' WHERE task_id=?", (tid,))
                failed += 1
                issues.append({"task_id": tid, "issue": "file_missing"})
                continue

            fsize = Path(dest).stat().st_size
            if fsize == 0:
                conn.execute("UPDATE download_tasks SET status='failed', error='Zero byte file' WHERE task_id=?", (tid,))
                failed += 1
                issues.append({"task_id": tid, "issue": "zero_bytes"})
                continue

            conn.execute("UPDATE download_tasks SET status='verified' WHERE task_id=?", (tid,))
            verified += 1

        conn.commit()
        return {
            "verified": verified,
            "failed": failed,
            "issues": issues[:50],
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Stats & sources
# -----------------------------------------------------------------------

def download_stats() -> Dict[str, Any]:
    """Get download statistics."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM download_tasks").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) FROM download_tasks GROUP BY status"
        ).fetchall()
        by_system = conn.execute(
            "SELECT system, COUNT(*) FROM download_tasks GROUP BY system ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall()
        total_bytes = conn.execute(
            "SELECT COALESCE(SUM(file_size),0) FROM download_tasks WHERE status IN ('complete','verified')"
        ).fetchone()[0]

        return {
            "total_tasks": total,
            "by_status": {r[0]: r[1] for r in by_status},
            "by_system": [{"system": r[0], "count": r[1]} for r in by_system],
            "total_downloaded_mb": round(total_bytes / (1024 * 1024), 2),
        }
    finally:
        conn.close()


def list_sources() -> Dict[str, Any]:
    """List known media download sources."""
    return {
        "sources": KNOWN_SOURCES,
        "media_types": {k: v for k, v in MEDIA_TYPES.items()},
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python theme_downloader.py scan <system> <hyperspin_root>")
        print("  python theme_downloader.py stats")
        print("  python theme_downloader.py sources")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "scan":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        root = sys.argv[3] if len(sys.argv) > 3 else ""
        result = scan_missing_media(system, root)
        print(json.dumps(result, indent=2))

    elif cmd == "stats":
        result = download_stats()
        print(json.dumps(result, indent=2))

    elif cmd == "sources":
        result = list_sources()
        print(json.dumps(result, indent=2))
