"""
M42 -- SWF Theme Conversion Pipeline

Converts Flash SWF themes to modern formats:
  - JPEXS CLI -> Lottie JSON for top animated themes
  - FFmpeg batch -> MP4 video loops for remaining SWF
  - Static PNG snapshot generation for thumbnails/previews
  - CefSharp fallback rendering for complex interactive SWF
  - Conversion status tracking and error reporting (SQLite)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("swf_converter")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "swf_conversions.db"

# Tool paths (configurable)
JPEXS_JAR = r"C:\Tools\jpexs\ffdec.jar"
FFMPEG_BIN = "ffmpeg"
JAVA_BIN = "java"

CONVERSION_FORMATS = ["lottie", "mp4", "png", "gif", "webm"]

OUTPUT_DIRS = {
    "lottie": "converted/lottie",
    "mp4": "converted/mp4",
    "png": "converted/png",
    "gif": "converted/gif",
    "webm": "converted/webm",
}


@dataclass
class ConversionTask:
    task_id: str = ""
    swf_path: str = ""
    system: str = ""
    game: str = ""
    target_format: str = "mp4"
    output_path: str = ""
    status: str = "pending"  # pending, running, completed, failed, skipped
    error: str = ""
    file_size_kb: float = 0
    duration_sec: float = 0
    created_at: str = ""
    completed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversionStats:
    total: int = 0
    pending: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total_input_mb: float = 0
    total_output_mb: float = 0
    by_format: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── SQLite ────────────────────────────────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversions (
            task_id TEXT PRIMARY KEY,
            swf_path TEXT NOT NULL,
            system TEXT DEFAULT '',
            game TEXT DEFAULT '',
            target_format TEXT DEFAULT 'mp4',
            output_path TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            error TEXT DEFAULT '',
            file_size_kb REAL DEFAULT 0,
            output_size_kb REAL DEFAULT 0,
            duration_sec REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            completed_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_conv_status ON conversions(status);
        CREATE INDEX IF NOT EXISTS idx_conv_system ON conversions(system);
    """)
    conn.commit()
    return conn


# ── Tool detection ───────────────────────────────────────────────────

def check_tools() -> Dict[str, Any]:
    """Check availability of conversion tools."""
    tools = {}

    # JPEXS
    jpexs_path = Path(JPEXS_JAR)
    tools["jpexs"] = {
        "available": jpexs_path.exists(),
        "path": str(jpexs_path),
        "install": "Download from https://github.com/niclasr/jpexs-decompiler/releases",
    }

    # FFmpeg
    ffmpeg_path = shutil.which(FFMPEG_BIN)
    tools["ffmpeg"] = {
        "available": ffmpeg_path is not None,
        "path": ffmpeg_path or "not found",
        "install": "winget install Gyan.FFmpeg or https://ffmpeg.org/download.html",
    }

    # Java (for JPEXS)
    java_path = shutil.which(JAVA_BIN)
    tools["java"] = {
        "available": java_path is not None,
        "path": java_path or "not found",
        "install": "winget install Oracle.JDK.21 or https://adoptium.net",
    }

    return {"tools": tools, "all_available": all(t["available"] for t in tools.values())}


# ── SWF scanning ─────────────────────────────────────────────────────

def scan_swf_themes(themes_dir: str, system: str = "") -> Dict[str, Any]:
    """Scan a directory for SWF theme files.

    Args:
        themes_dir: Directory to scan (e.g. D:\\Arcade\\HyperSpin\\Media\\MAME\\Themes)
        system: System name for tagging

    Returns:
        List of SWF files found with metadata
    """
    p = Path(themes_dir)
    if not p.exists():
        return {"error": f"Directory not found: {themes_dir}", "files": []}

    files = []
    total_size = 0
    for f in p.rglob("*.swf"):
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        total_size += size
        game = f.stem
        if not system:
            # Try to extract system from path
            parts = f.parts
            for i, part in enumerate(parts):
                if part.lower() in ("media", "themes"):
                    if i > 0:
                        system = parts[i - 1] if part.lower() == "themes" else ""
                    break

        files.append({
            "path": str(f),
            "game": game,
            "system": system,
            "size_kb": round(size / 1024, 1),
        })

    files.sort(key=lambda x: x["size_kb"], reverse=True)
    return {
        "directory": themes_dir,
        "system": system,
        "swf_count": len(files),
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "files": files,
    }


# ── Queue management ─────────────────────────────────────────────────

def queue_conversions(swf_paths: List[str], target_format: str = "mp4",
                      system: str = "", output_dir: str = "") -> Dict[str, Any]:
    """Queue SWF files for conversion.

    Args:
        swf_paths: List of SWF file paths
        target_format: Target format (lottie, mp4, png, gif, webm)
        system: System name for tagging
        output_dir: Output directory (auto-generated if empty)
    """
    if target_format not in CONVERSION_FORMATS:
        return {"error": f"Invalid format: {target_format}. Valid: {CONVERSION_FORMATS}"}

    if not output_dir:
        output_dir = str(TOOLKIT_ROOT / OUTPUT_DIRS.get(target_format, f"converted/{target_format}"))

    os.makedirs(output_dir, exist_ok=True)
    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    queued = 0
    skipped = 0

    try:
        for swf_path in swf_paths:
            p = Path(swf_path)
            if not p.exists() or p.suffix.lower() != ".swf":
                skipped += 1
                continue

            game = p.stem
            task_id = f"swf_{game}_{target_format}_{int(time.time() * 1000) % 1000000}"

            ext = ".json" if target_format == "lottie" else f".{target_format}"
            out_path = str(Path(output_dir) / f"{game}{ext}")

            try:
                size_kb = round(p.stat().st_size / 1024, 1)
            except OSError:
                size_kb = 0

            # Check if already queued
            existing = conn.execute(
                "SELECT task_id FROM conversions WHERE swf_path=? AND target_format=? AND status IN ('pending','completed')",
                (swf_path, target_format)
            ).fetchone()

            if existing:
                skipped += 1
                continue

            conn.execute("""
                INSERT INTO conversions (task_id, swf_path, system, game, target_format,
                    output_path, status, file_size_kb, created_at)
                VALUES (?,?,?,?,?,?,'pending',?,?)
            """, (task_id, swf_path, system, game, target_format, out_path, size_kb, now))
            queued += 1

        conn.commit()
    finally:
        conn.close()

    return {"queued": queued, "skipped": skipped, "target_format": target_format, "output_dir": output_dir}


def get_conversion_queue(status: str = "", limit: int = 50) -> Dict[str, Any]:
    """Get conversion queue entries."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM conversions"
        params: list = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM conversions LIMIT 0").description]
        return {"tasks": [dict(zip(cols, r)) for r in rows], "count": len(rows)}
    finally:
        conn.close()


# ── Conversion execution ─────────────────────────────────────────────

def _convert_swf_to_png(swf_path: str, output_path: str) -> Dict[str, Any]:
    """Convert SWF to static PNG snapshot using JPEXS."""
    jpexs = Path(JPEXS_JAR)
    if not jpexs.exists():
        return {"error": "JPEXS not found", "path": str(jpexs)}

    os.makedirs(Path(output_path).parent, exist_ok=True)
    try:
        result = subprocess.run(
            [JAVA_BIN, "-jar", str(jpexs), "-export", "image", str(Path(output_path).parent), swf_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return {"ok": True, "output": output_path}
        return {"error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "JPEXS timed out (60s)"}
    except Exception as e:
        return {"error": str(e)}


def _convert_swf_to_mp4(swf_path: str, output_path: str,
                         duration: int = 10, fps: int = 30) -> Dict[str, Any]:
    """Convert SWF to MP4 video loop using FFmpeg."""
    if not shutil.which(FFMPEG_BIN):
        return {"error": "FFmpeg not found"}

    os.makedirs(Path(output_path).parent, exist_ok=True)
    try:
        result = subprocess.run([
            FFMPEG_BIN, "-y", "-i", swf_path,
            "-t", str(duration), "-r", str(fps),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-an",
            output_path,
        ], capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and Path(output_path).exists():
            return {"ok": True, "output": output_path}
        return {"error": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "FFmpeg timed out (120s)"}
    except Exception as e:
        return {"error": str(e)}


def execute_conversion(task_id: str = "", batch_size: int = 5) -> Dict[str, Any]:
    """Execute pending conversions.

    Args:
        task_id: Specific task to run (empty = run next batch)
        batch_size: How many to process in this batch
    """
    conn = _ensure_db()
    try:
        if task_id:
            rows = conn.execute("SELECT * FROM conversions WHERE task_id=?", (task_id,)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM conversions WHERE status='pending' ORDER BY created_at LIMIT ?",
                (batch_size,)
            ).fetchall()

        if not rows:
            return {"message": "No pending conversions", "processed": 0}

        cols = [d[0] for d in conn.execute("SELECT * FROM conversions LIMIT 0").description]
        results = []

        for row in rows:
            task = dict(zip(cols, row))
            tid = task["task_id"]
            swf = task["swf_path"]
            fmt = task["target_format"]
            out = task["output_path"]

            conn.execute("UPDATE conversions SET status='running' WHERE task_id=?", (tid,))
            conn.commit()

            start = time.time()
            if fmt == "png":
                result = _convert_swf_to_png(swf, out)
            elif fmt in ("mp4", "webm"):
                result = _convert_swf_to_mp4(swf, out)
            elif fmt == "lottie":
                result = {"error": "Lottie conversion requires JPEXS + post-processing (not yet automated)"}
            else:
                result = {"error": f"Unsupported format: {fmt}"}

            elapsed = round(time.time() - start, 2)
            now = datetime.now(timezone.utc).isoformat()

            if result.get("ok"):
                out_size = 0
                try:
                    out_size = round(Path(out).stat().st_size / 1024, 1)
                except OSError:
                    pass
                conn.execute(
                    "UPDATE conversions SET status='completed', duration_sec=?, output_size_kb=?, completed_at=? WHERE task_id=?",
                    (elapsed, out_size, now, tid))
                result["task_id"] = tid
                result["duration_sec"] = elapsed
            else:
                conn.execute(
                    "UPDATE conversions SET status='failed', error=?, duration_sec=?, completed_at=? WHERE task_id=?",
                    (result.get("error", "unknown"), elapsed, now, tid))
                result["task_id"] = tid

            results.append(result)
            conn.commit()

        return {"processed": len(results), "results": results}
    finally:
        conn.close()


# ── Statistics ────────────────────────────────────────────────────────

def conversion_stats() -> Dict[str, Any]:
    """Get conversion statistics."""
    conn = _ensure_db()
    try:
        stats = ConversionStats()
        for status in ("pending", "completed", "failed", "skipped"):
            count = conn.execute("SELECT COUNT(*) FROM conversions WHERE status=?", (status,)).fetchone()[0]
            setattr(stats, status, count)
            stats.total += count

        row = conn.execute("SELECT SUM(file_size_kb), SUM(output_size_kb) FROM conversions").fetchone()
        stats.total_input_mb = round((row[0] or 0) / 1024, 1)
        stats.total_output_mb = round((row[1] or 0) / 1024, 1)

        for fmt_row in conn.execute("SELECT target_format, COUNT(*) FROM conversions GROUP BY target_format"):
            stats.by_format[fmt_row[0]] = fmt_row[1]

        return stats.to_dict()
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python swf_converter.py [tools|scan <dir>|stats]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "tools":
        print(json.dumps(check_tools(), indent=2))
    elif cmd == "scan" and len(sys.argv) > 2:
        print(json.dumps(scan_swf_themes(sys.argv[2]), indent=2))
    elif cmd == "stats":
        print(json.dumps(conversion_stats(), indent=2))
