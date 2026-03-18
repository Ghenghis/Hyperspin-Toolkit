"""
M27 -- ROM Set Completion Tracker

Provides:
  - Track completeness per system against known full sets (DAT files)
  - Missing ROM lists with file size estimates
  - Priority scoring (popular vs obscure titles)
  - Collection goal setting and progress tracking
  - Per-region completion breakdowns
  - SQLite persistent tracking
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("rom_completion")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "rom_completion.db"


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class SystemCompletion:
    """Completion status for a single system."""
    system: str
    total_in_dat: int = 0
    owned: int = 0
    missing: int = 0
    completion_pct: float = 0.0
    owned_size_mb: float = 0.0
    estimated_missing_size_mb: float = 0.0
    region_breakdown: Dict[str, Dict[str, int]] = field(default_factory=dict)
    top_missing: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CollectionGoal:
    """A user-defined collection goal."""
    goal_id: int = 0
    system: str = ""
    target_pct: float = 100.0
    target_count: int = 0
    region_filter: str = ""     # e.g. "USA" or "" for all
    priority: str = "medium"    # high, medium, low
    created_at: str = ""
    current_pct: float = 0.0
    current_count: int = 0
    status: str = "active"      # active, achieved, abandoned

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS completion_snapshots (
            snap_id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            total_in_dat INTEGER DEFAULT 0,
            owned INTEGER DEFAULT 0,
            missing INTEGER DEFAULT 0,
            completion_pct REAL DEFAULT 0,
            owned_size_bytes INTEGER DEFAULT 0,
            details_json TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS collection_goals (
            goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL,
            target_pct REAL DEFAULT 100,
            target_count INTEGER DEFAULT 0,
            region_filter TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            created_at TEXT NOT NULL,
            current_pct REAL DEFAULT 0,
            current_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        );

        CREATE TABLE IF NOT EXISTS missing_roms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL,
            rom_name TEXT NOT NULL,
            expected_size INTEGER DEFAULT 0,
            region TEXT DEFAULT '',
            priority_score REAL DEFAULT 0,
            dat_source TEXT DEFAULT '',
            timestamp TEXT NOT NULL,
            UNIQUE(system, rom_name)
        );

        CREATE INDEX IF NOT EXISTS idx_snap_system ON completion_snapshots(system);
        CREATE INDEX IF NOT EXISTS idx_snap_ts ON completion_snapshots(timestamp);
        CREATE INDEX IF NOT EXISTS idx_goal_system ON collection_goals(system);
        CREATE INDEX IF NOT EXISTS idx_missing_system ON missing_roms(system);
        CREATE INDEX IF NOT EXISTS idx_missing_priority ON missing_roms(priority_score);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# ROM name parsing helpers
# -----------------------------------------------------------------------

import re

REGION_PATTERN = re.compile(r"\((?:USA|US|Europe|EUR|Japan|JP|World|Korea|KR|France|FR|Germany|DE|Spain|ES|Italy|IT|Brazil|BR|Australia|AU)\)", re.I)

POPULAR_TITLES: Dict[str, List[str]] = {
    "NES": ["Super Mario Bros", "Zelda", "Mega Man", "Metroid", "Contra", "Castlevania", "Final Fantasy", "Dragon Quest", "Kirby", "Punch-Out"],
    "SNES": ["Super Mario World", "Zelda", "Chrono Trigger", "Final Fantasy", "Mega Man X", "Donkey Kong Country", "Super Metroid", "Street Fighter", "Earthbound", "Star Fox"],
    "Genesis": ["Sonic", "Streets of Rage", "Phantasy Star", "Shining Force", "Golden Axe", "Altered Beast", "Gunstar Heroes", "Comix Zone", "Shinobi", "Thunder Force"],
    "N64": ["Mario 64", "Ocarina of Time", "GoldenEye", "Mario Kart", "Smash Bros", "Banjo", "Perfect Dark", "Star Fox", "Paper Mario", "Majora"],
    "PlayStation": ["Final Fantasy", "Metal Gear", "Resident Evil", "Crash", "Spyro", "Tekken", "Tomb Raider", "Gran Turismo", "Castlevania", "Silent Hill"],
    "GBA": ["Pokemon", "Mario", "Zelda", "Metroid", "Fire Emblem", "Advance Wars", "Castlevania", "Mega Man", "Golden Sun", "Kirby"],
}


def _estimate_priority(rom_name: str, system: str) -> float:
    """Estimate priority score (0-100) for a missing ROM based on title popularity."""
    name_lower = rom_name.lower()
    popular = POPULAR_TITLES.get(system, [])

    score = 50.0  # baseline
    for title in popular:
        if title.lower() in name_lower:
            score = 90.0
            break

    # Boost for USA region
    if re.search(r"\(USA\)", rom_name, re.I):
        score += 5
    elif re.search(r"\(World\)", rom_name, re.I):
        score += 3

    # Penalize variants
    if re.search(r"\((?:Beta|Proto|Sample|Demo|Unl|Pirate|Hack)\)", rom_name, re.I):
        score -= 30

    # Penalize Rev/Alt
    if re.search(r"\(Rev\s*\w+\)", rom_name, re.I):
        score -= 10

    return max(0, min(100, score))


def _detect_region(rom_name: str) -> str:
    m = REGION_PATTERN.search(rom_name)
    if m:
        text = m.group(0).strip("()")
        for full, abbr in [("USA", "USA"), ("US", "USA"), ("Europe", "Europe"), ("EUR", "Europe"),
                           ("Japan", "Japan"), ("JP", "Japan"), ("World", "World")]:
            if text.upper() == full.upper():
                return abbr if abbr != full else full
        return text
    return "Unknown"


# -----------------------------------------------------------------------
# Completion tracking
# -----------------------------------------------------------------------

def check_completion(system: str, rom_dir: str,
                     dat_path: str = "", save_snapshot: bool = True) -> Dict[str, Any]:
    """Check ROM set completion for a system.

    Args:
        system: System name
        rom_dir: Directory containing ROMs
        dat_path: Optional DAT file for the full set
        save_snapshot: Whether to save result to DB

    Returns:
        Completion report with missing ROM list
    """
    rom_path = Path(rom_dir)
    if not rom_path.exists():
        return {"error": f"ROM directory not found: {rom_dir}"}

    # Get owned ROMs
    rom_extensions = {".zip", ".7z", ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba",
                      ".nds", ".gen", ".md", ".sms", ".gg", ".bin", ".iso", ".cue",
                      ".chd", ".cso", ".n64", ".z64", ".v64", ".a26", ".a78", ".pce",
                      ".ngp", ".col", ".fds", ".pbp", ".rar", ".gz"}

    owned_files: Dict[str, int] = {}
    for f in rom_path.rglob("*"):
        if f.is_file() and f.suffix.lower() in rom_extensions:
            owned_files[f.stem.lower()] = f.stat().st_size

    owned_count = len(owned_files)
    owned_size = sum(owned_files.values())

    # Get full set from DAT if available
    dat_entries: List[Dict[str, str]] = []
    if dat_path and Path(dat_path).exists():
        dat_entries = _parse_dat_names(dat_path)
    else:
        # Try to load from dat_verifier
        try:
            from engines.dat_verifier import find_dat_for_system
            found_dat = find_dat_for_system(system)
            if found_dat:
                dat_entries = _parse_dat_names(found_dat)
        except Exception:
            pass

    if not dat_entries:
        # No DAT: report owned only
        return {
            "system": system,
            "owned": owned_count,
            "owned_size_mb": round(owned_size / (1024 * 1024), 2),
            "total_in_dat": 0,
            "completion_pct": 0,
            "message": "No DAT file found — cannot calculate completion. Provide a DAT path.",
        }

    total_in_dat = len(dat_entries)

    # Match owned vs DAT
    dat_names_lower = {e["name"].lower(): e for e in dat_entries}
    owned_lower = set(owned_files.keys())

    matched = owned_lower & set(dat_names_lower.keys())
    missing_names = set(dat_names_lower.keys()) - owned_lower

    missing_roms = []
    region_breakdown: Dict[str, Dict[str, int]] = defaultdict(lambda: {"total": 0, "owned": 0, "missing": 0})

    for name in missing_names:
        entry = dat_names_lower[name]
        region = _detect_region(entry.get("name", name))
        priority = _estimate_priority(entry.get("name", name), system)
        est_size = int(entry.get("size", 0))

        missing_roms.append({
            "rom_name": entry.get("name", name),
            "region": region,
            "priority_score": round(priority, 1),
            "estimated_size": est_size,
        })

        region_breakdown[region]["total"] += 1
        region_breakdown[region]["missing"] += 1

    for name in matched:
        entry = dat_names_lower[name]
        region = _detect_region(entry.get("name", name))
        region_breakdown[region]["total"] += 1
        region_breakdown[region]["owned"] += 1

    # Sort missing by priority
    missing_roms.sort(key=lambda r: r["priority_score"], reverse=True)

    completion_pct = round(len(matched) / total_in_dat * 100, 1) if total_in_dat > 0 else 0
    est_missing_size = sum(r.get("estimated_size", 0) for r in missing_roms)

    result = SystemCompletion(
        system=system,
        total_in_dat=total_in_dat,
        owned=len(matched),
        missing=len(missing_names),
        completion_pct=completion_pct,
        owned_size_mb=round(owned_size / (1024 * 1024), 2),
        estimated_missing_size_mb=round(est_missing_size / (1024 * 1024), 2),
        region_breakdown=dict(region_breakdown),
        top_missing=missing_roms[:30],
    )

    # Save snapshot
    if save_snapshot:
        _save_snapshot(result)
        _save_missing(system, missing_roms)

    return result.to_dict()


def _parse_dat_names(dat_path: str) -> List[Dict[str, str]]:
    """Parse ROM names from a DAT file (No-Intro/Redump/TOSEC XML or CLRMAMEPro)."""
    path = Path(dat_path)
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="replace")
    entries = []

    if text.strip().startswith("<?xml") or "<datafile" in text[:500]:
        # XML DAT
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
            for game in root.findall(".//game"):
                name = game.get("name", "")
                rom = game.find("rom")
                size = rom.get("size", "0") if rom is not None else "0"
                entries.append({"name": name, "size": size})
        except ET.ParseError:
            pass
    else:
        # CLRMAMEPro format
        for match in re.finditer(r'game\s*\(\s*name\s+"([^"]+)"', text):
            entries.append({"name": match.group(1), "size": "0"})

    return entries


def _save_snapshot(sc: SystemCompletion):
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT INTO completion_snapshots
            (system, timestamp, total_in_dat, owned, missing, completion_pct, owned_size_bytes, details_json)
            VALUES (?,?,?,?,?,?,?,?)
        """, (sc.system, datetime.now(timezone.utc).isoformat(), sc.total_in_dat,
              sc.owned, sc.missing, sc.completion_pct,
              int(sc.owned_size_mb * 1024 * 1024),
              json.dumps(sc.region_breakdown)))
        conn.commit()
    finally:
        conn.close()


def _save_missing(system: str, missing_roms: List[Dict]):
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("DELETE FROM missing_roms WHERE system=?", (system,))
        for r in missing_roms:
            conn.execute("""
                INSERT OR REPLACE INTO missing_roms
                (system, rom_name, expected_size, region, priority_score, timestamp)
                VALUES (?,?,?,?,?,?)
            """, (system, r["rom_name"], r.get("estimated_size", 0),
                  r.get("region", ""), r.get("priority_score", 50), now))
        conn.commit()
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Goals
# -----------------------------------------------------------------------

def set_goal(system: str, target_pct: float = 100.0, target_count: int = 0,
             region_filter: str = "", priority: str = "medium") -> CollectionGoal:
    """Set a collection goal for a system."""
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("""
            INSERT INTO collection_goals
            (system, target_pct, target_count, region_filter, priority, created_at, status)
            VALUES (?,?,?,?,?,?,'active')
        """, (system, target_pct, target_count, region_filter, priority, now))
        conn.commit()
        return CollectionGoal(
            goal_id=cur.lastrowid, system=system, target_pct=target_pct,
            target_count=target_count, region_filter=region_filter,
            priority=priority, created_at=now, status="active",
        )
    finally:
        conn.close()


def get_goals(system: str = "", active_only: bool = True) -> List[CollectionGoal]:
    """Get collection goals."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM collection_goals WHERE 1=1"
        params: list = []
        if system:
            sql += " AND system=?"
            params.append(system)
        if active_only:
            sql += " AND status='active'"
        sql += " ORDER BY priority DESC, system"
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM collection_goals LIMIT 0").description]
        return [CollectionGoal(**dict(zip(cols, r))) for r in rows]
    finally:
        conn.close()


def check_goal_progress() -> Dict[str, Any]:
    """Check progress on all active goals against latest snapshots."""
    conn = _ensure_db()
    try:
        goals = get_goals(active_only=True)
        results = []
        for g in goals:
            # Get latest snapshot
            row = conn.execute(
                "SELECT completion_pct, owned FROM completion_snapshots WHERE system=? ORDER BY timestamp DESC LIMIT 1",
                (g.system,)
            ).fetchone()
            if row:
                g.current_pct = row[0]
                g.current_count = row[1]

            achieved = False
            if g.target_pct > 0 and g.current_pct >= g.target_pct:
                achieved = True
            if g.target_count > 0 and g.current_count >= g.target_count:
                achieved = True

            if achieved and g.status == "active":
                conn.execute("UPDATE collection_goals SET status='achieved', current_pct=?, current_count=? WHERE goal_id=?",
                             (g.current_pct, g.current_count, g.goal_id))
                g.status = "achieved"

            results.append({
                **g.to_dict(),
                "progress": round(g.current_pct / g.target_pct * 100, 1) if g.target_pct > 0 else 0,
                "achieved": achieved,
            })

        conn.commit()
        return {
            "goals": results,
            "total": len(results),
            "achieved": sum(1 for r in results if r["achieved"]),
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Missing ROM queries
# -----------------------------------------------------------------------

def get_missing_roms(system: str, limit: int = 50,
                     region: str = "", min_priority: float = 0) -> Dict[str, Any]:
    """Get missing ROMs for a system, sorted by priority."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM missing_roms WHERE system=?"
        params: list = [system]
        if region:
            sql += " AND region=?"
            params.append(region)
        if min_priority > 0:
            sql += " AND priority_score>=?"
            params.append(min_priority)
        sql += " ORDER BY priority_score DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM missing_roms LIMIT 0").description]
        entries = [dict(zip(cols, r)) for r in rows]

        total = conn.execute("SELECT COUNT(*) FROM missing_roms WHERE system=?", (system,)).fetchone()[0]

        return {
            "system": system,
            "total_missing": total,
            "showing": len(entries),
            "missing_roms": entries,
        }
    finally:
        conn.close()


def get_completion_history(system: str, limit: int = 20) -> Dict[str, Any]:
    """Get completion history snapshots for a system."""
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT timestamp, total_in_dat, owned, missing, completion_pct FROM completion_snapshots "
            "WHERE system=? ORDER BY timestamp DESC LIMIT ?",
            (system, limit)
        ).fetchall()
        return {
            "system": system,
            "snapshots": [
                {"timestamp": r[0], "total": r[1], "owned": r[2], "missing": r[3], "pct": r[4]}
                for r in rows
            ],
        }
    finally:
        conn.close()


def completion_overview() -> Dict[str, Any]:
    """Get completion overview across all tracked systems."""
    conn = _ensure_db()
    try:
        # Latest snapshot per system
        rows = conn.execute("""
            SELECT s.system, s.total_in_dat, s.owned, s.missing, s.completion_pct, s.owned_size_bytes
            FROM completion_snapshots s
            INNER JOIN (
                SELECT system, MAX(timestamp) as max_ts FROM completion_snapshots GROUP BY system
            ) latest ON s.system = latest.system AND s.timestamp = latest.max_ts
            ORDER BY s.completion_pct DESC
        """).fetchall()

        systems = []
        total_owned = 0
        total_in_dat = 0
        total_size = 0

        for r in rows:
            systems.append({
                "system": r[0], "total_in_dat": r[1], "owned": r[2],
                "missing": r[3], "completion_pct": r[4],
                "owned_size_mb": round(r[5] / (1024 * 1024), 2) if r[5] else 0,
            })
            total_owned += r[2]
            total_in_dat += r[1]
            total_size += (r[5] or 0)

        return {
            "systems_tracked": len(systems),
            "total_owned": total_owned,
            "total_in_dat": total_in_dat,
            "overall_pct": round(total_owned / total_in_dat * 100, 1) if total_in_dat > 0 else 0,
            "total_size_gb": round(total_size / (1024 ** 3), 2),
            "per_system": systems,
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
        print("  python rom_completion.py check <system> <rom_dir> [dat_path]")
        print("  python rom_completion.py overview")
        print("  python rom_completion.py missing <system>")
        print("  python rom_completion.py goal <system> <target_pct>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        rom_dir = sys.argv[3] if len(sys.argv) > 3 else ""
        dat = sys.argv[4] if len(sys.argv) > 4 else ""
        if not system or not rom_dir:
            print("Need: system rom_dir [dat_path]")
        else:
            result = check_completion(system, rom_dir, dat)
            print(json.dumps(result, indent=2))

    elif cmd == "overview":
        result = completion_overview()
        print(json.dumps(result, indent=2))

    elif cmd == "missing":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        result = get_missing_roms(system)
        print(json.dumps(result, indent=2))

    elif cmd == "goal":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        pct = float(sys.argv[3]) if len(sys.argv) > 3 else 100.0
        goal = set_goal(system, pct)
        print(f"Goal set: {goal.to_dict()}")
