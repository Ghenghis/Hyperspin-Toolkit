"""
M53 -- Drive Manifest & Deep Indexer Engine
Complete the Drive Indexer milestone with:
  - Deep recursive scanning (path, size, hash, file type)
  - SQLite drive_index table with full-text search
  - Per-drive JSON manifest export (saved to drive root)
  - Cross-drive duplicate file detection
  - Integration with drive_index.py fingerprints and drive_indexer.py detection

Builds on:
  - drive_index.py: fingerprint identity, reconciliation, role mgmt
  - drive_indexer.py: collection type detection, registry, PS enumeration
  - drive_fingerprint.py (M64): KINHANK variant detection
"""

import csv
import hashlib
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

logger = logging.getLogger("drive_manifest")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "drive_index.db"

# File type classification by extension
FILE_TYPES = {
    "rom": {
        ".zip", ".7z", ".nes", ".snes", ".sfc", ".smc", ".gba", ".gbc", ".gb",
        ".nds", ".3ds", ".cia", ".n64", ".z64", ".v64", ".gen", ".md", ".sms",
        ".gg", ".pce", ".ngp", ".ngc", ".ws", ".wsc", ".a26", ".a78", ".lnx",
        ".jag", ".col", ".sg", ".int", ".vec", ".bin",
    },
    "disc_image": {
        ".iso", ".cue", ".chd", ".cso", ".pbp", ".mdf", ".mds", ".nrg",
        ".gcz", ".rvz", ".wbfs", ".wia", ".pkg", ".vpk", ".xci", ".nsp",
        ".nsz", ".xiso",
    },
    "media": {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".tga",
        ".mp4", ".avi", ".mkv", ".flv", ".wmv", ".mp3", ".ogg", ".wav",
        ".flac",
    },
    "config": {
        ".ini", ".cfg", ".xml", ".yaml", ".yml", ".json", ".toml", ".conf",
        ".properties", ".reg",
    },
    "executable": {
        ".exe", ".bat", ".cmd", ".ps1", ".sh", ".msi", ".dll", ".so",
    },
    "archive": {
        ".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".zst",
    },
    "document": {
        ".txt", ".md", ".pdf", ".doc", ".docx", ".rtf", ".html", ".htm",
    },
}


def classify_file(ext: str) -> str:
    """Classify a file extension into a category."""
    ext = ext.lower()
    for category, extensions in FILE_TYPES.items():
        if ext in extensions:
            return category
    return "other"


# ---------------------------------------------------------------------------
# SQLite schema & connection
# ---------------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    """Create/open the SQLite database and ensure schema exists."""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS drive_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_letter TEXT NOT NULL,
            fingerprint TEXT,
            rel_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            file_type TEXT,
            size_bytes INTEGER DEFAULT 0,
            md5_hash TEXT,
            modified_at TEXT,
            indexed_at TEXT NOT NULL,
            UNIQUE(drive_letter, rel_path)
        );

        CREATE TABLE IF NOT EXISTS drive_manifests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            drive_letter TEXT NOT NULL,
            fingerprint TEXT,
            label TEXT,
            collection_type TEXT,
            total_files INTEGER DEFAULT 0,
            total_dirs INTEGER DEFAULT 0,
            total_size_bytes INTEGER DEFAULT 0,
            scan_duration_sec REAL DEFAULT 0,
            scanned_at TEXT NOT NULL,
            manifest_json TEXT,
            UNIQUE(drive_letter)
        );

        CREATE INDEX IF NOT EXISTS idx_files_drive ON drive_files(drive_letter);
        CREATE INDEX IF NOT EXISTS idx_files_ext ON drive_files(extension);
        CREATE INDEX IF NOT EXISTS idx_files_hash ON drive_files(md5_hash);
        CREATE INDEX IF NOT EXISTS idx_files_type ON drive_files(file_type);
        CREATE INDEX IF NOT EXISTS idx_files_size ON drive_files(size_bytes);

        CREATE VIRTUAL TABLE IF NOT EXISTS drive_files_fts USING fts5(
            rel_path, filename, file_type,
            content=drive_files,
            content_rowid=id
        );

        CREATE TRIGGER IF NOT EXISTS drive_files_ai AFTER INSERT ON drive_files BEGIN
            INSERT INTO drive_files_fts(rowid, rel_path, filename, file_type)
            VALUES (new.id, new.rel_path, new.filename, new.file_type);
        END;

        CREATE TRIGGER IF NOT EXISTS drive_files_ad AFTER DELETE ON drive_files BEGIN
            INSERT INTO drive_files_fts(drive_files_fts, rowid, rel_path, filename, file_type)
            VALUES ('delete', old.id, old.rel_path, old.filename, old.file_type);
        END;

        CREATE TRIGGER IF NOT EXISTS drive_files_au AFTER UPDATE ON drive_files BEGIN
            INSERT INTO drive_files_fts(drive_files_fts, rowid, rel_path, filename, file_type)
            VALUES ('delete', old.id, old.rel_path, old.filename, old.file_type);
            INSERT INTO drive_files_fts(rowid, rel_path, filename, file_type)
            VALUES (new.id, new.rel_path, new.filename, new.file_type);
        END;
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Deep recursive scanner
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    "$Recycle.Bin", "System Volume Information", "$RECYCLE.BIN",
    "Recovery", "ProgramData", "Windows", "$Windows.~BT",
}


@dataclass
class ScanStats:
    """Accumulated stats during a deep scan."""
    total_files: int = 0
    total_dirs: int = 0
    total_size_bytes: int = 0
    files_by_type: Dict[str, int] = field(default_factory=dict)
    size_by_type: Dict[str, int] = field(default_factory=dict)
    largest_files: List[Dict] = field(default_factory=list)
    zero_byte_files: int = 0
    errors: List[str] = field(default_factory=list)


def _file_md5(path: Path, max_bytes: int = 64 * 1024) -> str:
    """Compute partial MD5 hash (first 64KB) for speed."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            h.update(f.read(max_bytes))
    except Exception:
        return ""
    return h.hexdigest()


def deep_scan(drive_letter: str, *,
              hash_files: bool = False,
              max_depth: int = 0,
              skip_dirs: Optional[Set[str]] = None,
              progress_callback=None) -> Tuple[List[Dict], ScanStats]:
    """
    Deep recursive scan of an entire drive.

    Args:
        drive_letter: Drive letter (e.g. 'D')
        hash_files: Compute partial MD5 for each file (slower)
        max_depth: Max directory depth (0 = unlimited)
        skip_dirs: Additional directory names to skip
        progress_callback: Called with (files_so_far, current_path) periodically

    Returns:
        (file_records, scan_stats)
    """
    letter = drive_letter.strip().rstrip(":").upper()
    root = Path(f"{letter}:\\")
    if not root.exists():
        return [], ScanStats(errors=[f"Drive {letter}:\\ not found"])

    skips = SKIP_DIRS | (skip_dirs or set())
    stats = ScanStats()
    records: List[Dict] = []
    now = datetime.now(timezone.utc).isoformat()
    report_interval = 5000  # report progress every N files

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Filter out skip dirs in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in skips and not d.startswith("$")
        ]

        # Depth check
        rel_dir = os.path.relpath(dirpath, root)
        if max_depth > 0:
            depth = 0 if rel_dir == "." else rel_dir.count(os.sep) + 1
            if depth >= max_depth:
                dirnames.clear()

        stats.total_dirs += 1

        for fname in filenames:
            fpath = Path(dirpath) / fname
            rel_path = str(fpath.relative_to(root))
            ext = fpath.suffix.lower()
            ftype = classify_file(ext)

            try:
                fsize = fpath.stat().st_size
                mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc).isoformat()
            except (OSError, PermissionError) as e:
                stats.errors.append(f"{rel_path}: {e}")
                continue

            md5 = ""
            if hash_files and fsize > 0:
                md5 = _file_md5(fpath)

            record = {
                "drive_letter": letter,
                "rel_path": rel_path,
                "filename": fname,
                "extension": ext,
                "file_type": ftype,
                "size_bytes": fsize,
                "md5_hash": md5,
                "modified_at": mtime,
                "indexed_at": now,
            }
            records.append(record)

            # Stats
            stats.total_files += 1
            stats.total_size_bytes += fsize
            stats.files_by_type[ftype] = stats.files_by_type.get(ftype, 0) + 1
            stats.size_by_type[ftype] = stats.size_by_type.get(ftype, 0) + fsize

            if fsize == 0:
                stats.zero_byte_files += 1

            # Track largest files (keep top 20)
            if len(stats.largest_files) < 20 or fsize > stats.largest_files[-1].get("size_bytes", 0):
                stats.largest_files.append({
                    "path": rel_path,
                    "size_bytes": fsize,
                    "size_human": _human_size(fsize),
                    "type": ftype,
                })
                stats.largest_files.sort(key=lambda x: -x["size_bytes"])
                stats.largest_files = stats.largest_files[:20]

            if progress_callback and stats.total_files % report_interval == 0:
                progress_callback(stats.total_files, rel_path)

    return records, stats


# ---------------------------------------------------------------------------
# Index to SQLite
# ---------------------------------------------------------------------------

def index_drive(drive_letter: str, *,
                fingerprint: str = "",
                hash_files: bool = False,
                max_depth: int = 0,
                progress_callback=None) -> Dict[str, Any]:
    """
    Full deep scan + SQLite indexing of a drive.

    Returns summary dict with stats, duration, and file counts.
    """
    letter = drive_letter.strip().rstrip(":").upper()
    logger.info("Starting deep index of %s:\\ (hash=%s, depth=%s)", letter, hash_files, max_depth or "unlimited")

    t0 = time.time()
    records, stats = deep_scan(
        letter,
        hash_files=hash_files,
        max_depth=max_depth,
        progress_callback=progress_callback,
    )
    scan_time = time.time() - t0

    if not records:
        return {
            "drive": letter,
            "error": stats.errors[0] if stats.errors else "No files found",
            "duration_sec": round(scan_time, 1),
        }

    # Store in SQLite
    conn = _ensure_db()
    try:
        # Clear old records for this drive
        conn.execute("DELETE FROM drive_files WHERE drive_letter = ?", (letter,))

        # Bulk insert
        conn.executemany(
            """INSERT OR REPLACE INTO drive_files
               (drive_letter, fingerprint, rel_path, filename, extension,
                file_type, size_bytes, md5_hash, modified_at, indexed_at)
               VALUES (:drive_letter, :fingerprint, :rel_path, :filename, :extension,
                       :file_type, :size_bytes, :md5_hash, :modified_at, :indexed_at)""",
            [{**r, "fingerprint": fingerprint} for r in records],
        )

        # Get collection type from drive_indexer
        try:
            from engines.drive_indexer import detect_collection_type
            collection_type = detect_collection_type(f"{letter}:\\")
        except Exception:
            collection_type = "Unknown"

        # Get label
        label = ""
        try:
            from engines.drive_index import _get_volume_label
            label = _get_volume_label(letter)
        except Exception:
            pass

        # Store manifest summary
        manifest_data = {
            "drive_letter": letter,
            "fingerprint": fingerprint,
            "label": label,
            "collection_type": collection_type,
            "total_files": stats.total_files,
            "total_dirs": stats.total_dirs,
            "total_size_bytes": stats.total_size_bytes,
            "total_size_human": _human_size(stats.total_size_bytes),
            "files_by_type": stats.files_by_type,
            "size_by_type": {k: _human_size(v) for k, v in stats.size_by_type.items()},
            "largest_files": stats.largest_files[:10],
            "zero_byte_files": stats.zero_byte_files,
            "scan_errors": len(stats.errors),
            "scan_duration_sec": round(scan_time, 1),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

        conn.execute(
            """INSERT OR REPLACE INTO drive_manifests
               (drive_letter, fingerprint, label, collection_type,
                total_files, total_dirs, total_size_bytes,
                scan_duration_sec, scanned_at, manifest_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (letter, fingerprint, label, collection_type,
             stats.total_files, stats.total_dirs, stats.total_size_bytes,
             round(scan_time, 1), manifest_data["scanned_at"],
             json.dumps(manifest_data, indent=2)),
        )

        conn.commit()
        logger.info("Indexed %s:\\ -> %d files, %s in %.1fs",
                     letter, stats.total_files, _human_size(stats.total_size_bytes), scan_time)

        return manifest_data

    except Exception as e:
        logger.error("Failed to store index for %s: %s", letter, e)
        return {"drive": letter, "error": str(e)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Per-drive JSON manifest export
# ---------------------------------------------------------------------------

def export_manifest(drive_letter: str, output_path: Optional[str] = None) -> str:
    """
    Export the drive manifest as a JSON file.
    Default: save to <drive>:\\.drive_manifest.json
    """
    letter = drive_letter.strip().rstrip(":").upper()
    if output_path is None:
        output_path = f"{letter}:\\.drive_manifest.json"

    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT manifest_json FROM drive_manifests WHERE drive_letter = ?",
            (letter,)
        ).fetchone()

        if not row:
            return f"No manifest found for {letter}:\\ -- run index_drive first"

        manifest = json.loads(row[0])

        # Add file listing summary (top-level tree)
        rows = conn.execute(
            """SELECT rel_path, size_bytes, file_type FROM drive_files
               WHERE drive_letter = ? AND rel_path NOT LIKE '%\\%'
               ORDER BY filename""",
            (letter,)
        ).fetchall()
        manifest["top_level_files"] = [
            {"path": r[0], "size": _human_size(r[1]), "type": r[2]} for r in rows
        ]

        # Add directory summary
        dir_rows = conn.execute(
            """SELECT
                 CASE WHEN INSTR(rel_path, '\\') > 0
                      THEN SUBSTR(rel_path, 1, INSTR(rel_path, '\\') - 1)
                      ELSE rel_path END AS top_dir,
                 COUNT(*) as file_count,
                 SUM(size_bytes) as total_size
               FROM drive_files WHERE drive_letter = ?
               GROUP BY top_dir ORDER BY total_size DESC""",
            (letter,)
        ).fetchall()
        manifest["directory_summary"] = [
            {"dir": r[0], "files": r[1], "size": _human_size(r[2])} for r in dir_rows
        ]

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info("Exported manifest: %s", output_path)
        return output_path

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------

def search_files(query: str, drive_letter: Optional[str] = None,
                 file_type: Optional[str] = None,
                 limit: int = 50) -> List[Dict]:
    """
    Search indexed files using full-text search.

    Args:
        query: Search string (filename, path fragment)
        drive_letter: Restrict to a specific drive (optional)
        file_type: Filter by type: rom, disc_image, media, config, etc.
        limit: Max results

    Returns:
        List of matching file records
    """
    conn = _ensure_db()
    try:
        # Build FTS query
        sql = """
            SELECT df.drive_letter, df.rel_path, df.filename, df.extension,
                   df.file_type, df.size_bytes, df.md5_hash, df.modified_at
            FROM drive_files_fts fts
            JOIN drive_files df ON df.id = fts.rowid
            WHERE fts.drive_files_fts MATCH ?
        """
        params: list = [query]

        if drive_letter:
            sql += " AND df.drive_letter = ?"
            params.append(drive_letter.strip().rstrip(":").upper())
        if file_type:
            sql += " AND df.file_type = ?"
            params.append(file_type)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "drive": r[0], "path": r[1], "filename": r[2],
                "ext": r[3], "type": r[4], "size": _human_size(r[5]),
                "size_bytes": r[5], "md5": r[6], "modified": r[7],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error("Search error: %s", e)
        return [{"error": str(e)}]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cross-drive duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(drives: Optional[List[str]] = None, *,
                    min_size_bytes: int = 1024 * 1024,
                    use_hash: bool = True,
                    file_types: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Find duplicate files across indexed drives.

    Args:
        drives: List of drive letters to compare (None = all indexed)
        min_size_bytes: Minimum file size to consider (default 1MB)
        use_hash: Use MD5 hash for matching (requires hash_files=True during index)
        file_types: Only check these file types (e.g. ["rom", "disc_image"])

    Returns:
        Dict with duplicate groups, wasted space, and recommendations
    """
    conn = _ensure_db()
    try:
        # Strategy: group by (filename + size) or (md5_hash) across drives
        if use_hash:
            sql = """
                SELECT md5_hash, filename, size_bytes, drive_letter, rel_path
                FROM drive_files
                WHERE md5_hash != '' AND md5_hash IS NOT NULL
                  AND size_bytes >= ?
            """
            params: list = [min_size_bytes]
        else:
            sql = """
                SELECT filename || '|' || CAST(size_bytes AS TEXT) as match_key,
                       filename, size_bytes, drive_letter, rel_path
                FROM drive_files
                WHERE size_bytes >= ?
            """
            params = [min_size_bytes]

        if drives:
            placeholders = ",".join("?" * len(drives))
            sql += f" AND drive_letter IN ({placeholders})"
            params.extend([d.strip().rstrip(":").upper() for d in drives])

        if file_types:
            placeholders = ",".join("?" * len(file_types))
            sql += f" AND file_type IN ({placeholders})"
            params.extend(file_types)

        sql += " ORDER BY 1, 4"
        rows = conn.execute(sql, params).fetchall()

        # Group by match key
        groups: Dict[str, List[Dict]] = {}
        for r in rows:
            key = r[0]
            groups.setdefault(key, []).append({
                "filename": r[1],
                "size_bytes": r[2],
                "drive": r[3],
                "path": r[4],
            })

        # Filter to actual duplicates (>1 occurrence, across different drives)
        duplicates = []
        total_wasted = 0
        for key, items in groups.items():
            drive_set = set(i["drive"] for i in items)
            if len(items) > 1 and len(drive_set) > 1:
                size = items[0]["size_bytes"]
                wasted = size * (len(items) - 1)
                total_wasted += wasted
                duplicates.append({
                    "filename": items[0]["filename"],
                    "size": _human_size(size),
                    "size_bytes": size,
                    "copies": len(items),
                    "drives": sorted(drive_set),
                    "wasted": _human_size(wasted),
                    "locations": [f"{i['drive']}:\\{i['path']}" for i in items],
                })

        duplicates.sort(key=lambda x: -x["size_bytes"])

        return {
            "duplicate_groups": len(duplicates),
            "total_duplicate_files": sum(d["copies"] for d in duplicates),
            "total_wasted_space": _human_size(total_wasted),
            "total_wasted_bytes": total_wasted,
            "top_duplicates": duplicates[:50],
            "drives_compared": drives or "all indexed",
        }

    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_drive_stats(drive_letter: Optional[str] = None) -> List[Dict]:
    """Get indexed stats for one or all drives."""
    conn = _ensure_db()
    try:
        if drive_letter:
            rows = conn.execute(
                "SELECT * FROM drive_manifests WHERE drive_letter = ?",
                (drive_letter.strip().rstrip(":").upper(),)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM drive_manifests ORDER BY drive_letter").fetchall()

        cols = [d[0] for d in conn.execute("SELECT * FROM drive_manifests LIMIT 0").description]
        results = []
        for row in rows:
            d = dict(zip(cols, row))
            d["total_size_human"] = _human_size(d.get("total_size_bytes", 0))
            if d.get("manifest_json"):
                d["manifest"] = json.loads(d["manifest_json"])
                del d["manifest_json"]
            results.append(d)
        return results
    finally:
        conn.close()


def file_type_breakdown(drive_letter: str) -> Dict:
    """Get file type breakdown for a specific drive."""
    conn = _ensure_db()
    letter = drive_letter.strip().rstrip(":").upper()
    try:
        rows = conn.execute(
            """SELECT file_type, COUNT(*) as cnt, SUM(size_bytes) as total
               FROM drive_files WHERE drive_letter = ?
               GROUP BY file_type ORDER BY total DESC""",
            (letter,)
        ).fetchall()
        return {
            "drive": letter,
            "breakdown": [
                {"type": r[0], "count": r[1], "size": _human_size(r[2]), "size_bytes": r[2]}
                for r in rows
            ],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _human_size(n: int) -> str:
    """Convert bytes to human-readable size string."""
    if n < 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python drive_manifest.py index <drive> [--hash] [--depth N]")
        print("  python drive_manifest.py export <drive> [output.json]")
        print("  python drive_manifest.py search <query> [--drive X] [--type rom]")
        print("  python drive_manifest.py duplicates [drive1 drive2 ...] [--min-size 1048576]")
        print("  python drive_manifest.py stats [drive]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "index":
        drv = sys.argv[2] if len(sys.argv) > 2 else "D"
        do_hash = "--hash" in sys.argv
        depth = 0
        if "--depth" in sys.argv:
            idx = sys.argv.index("--depth")
            depth = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 0
        def _progress(n, path):
            print(f"  [{n:,} files] {path[:80]}")
        result = index_drive(drv, hash_files=do_hash, max_depth=depth, progress_callback=_progress)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "export":
        drv = sys.argv[2] if len(sys.argv) > 2 else "D"
        out = sys.argv[3] if len(sys.argv) > 3 else None
        path = export_manifest(drv, out)
        print(f"Manifest exported: {path}")

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        drv = None
        ftype = None
        if "--drive" in sys.argv:
            idx = sys.argv.index("--drive")
            drv = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if "--type" in sys.argv:
            idx = sys.argv.index("--type")
            ftype = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        results = search_files(q, drv, ftype)
        for r in results:
            print(f"  {r['drive']}:\\{r['path']}  ({r['size']}, {r['type']})")

    elif cmd == "duplicates":
        drives = [a for a in sys.argv[2:] if not a.startswith("--")]
        min_sz = 1024 * 1024
        if "--min-size" in sys.argv:
            idx = sys.argv.index("--min-size")
            min_sz = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else min_sz
        result = find_duplicates(drives or None, min_size_bytes=min_sz)
        print(f"Found {result['duplicate_groups']} duplicate groups")
        print(f"Wasted space: {result['total_wasted_space']}")
        for d in result["top_duplicates"][:10]:
            print(f"  {d['filename']} ({d['size']}) x{d['copies']} on {d['drives']}")

    elif cmd == "stats":
        drv = sys.argv[2] if len(sys.argv) > 2 else None
        stats = get_drive_stats(drv)
        for s in stats:
            print(f"  {s['drive_letter']}: {s.get('total_files', 0):,} files, "
                  f"{s.get('total_size_human', '?')}, type={s.get('collection_type', '?')}")
    else:
        print(f"Unknown command: {cmd}")
