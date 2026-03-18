"""
M34 -- Full Ecosystem Health Score

Provides:
  - Aggregate score (0-100) for entire HyperSpin setup
  - Weighted scoring across all subsystems (BIOS, ROMs, media, config, emulators)
  - Trend tracking over time via SQLite snapshots
  - Actionable improvement suggestions with priority
  - AI-generated health report narrative
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("health_score")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "health_scores.db"

# Subsystem weights (must sum to 1.0)
WEIGHTS = {
    "bios": 0.15,
    "roms": 0.20,
    "media": 0.15,
    "emulators": 0.15,
    "config": 0.10,
    "integrity": 0.10,
    "completion": 0.10,
    "scheduler": 0.05,
}


@dataclass
class SubsystemScore:
    """Score for a single subsystem."""
    name: str
    score: float = 0.0          # 0-100
    weight: float = 0.0
    weighted_score: float = 0.0
    details: str = ""
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    """Complete ecosystem health report."""
    overall_score: float = 0.0
    grade: str = ""             # A+ to F
    subsystems: List[SubsystemScore] = field(default_factory=list)
    top_issues: List[str] = field(default_factory=list)
    top_suggestions: List[str] = field(default_factory=list)
    narrative: str = ""
    timestamp: str = ""
    trend: str = ""             # improving, stable, declining

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
        CREATE TABLE IF NOT EXISTS health_snapshots (
            snap_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            overall_score REAL DEFAULT 0,
            grade TEXT DEFAULT '',
            subsystems_json TEXT DEFAULT '[]',
            narrative TEXT DEFAULT '',
            trend TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_health_ts ON health_snapshots(timestamp);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Grade calculation
# -----------------------------------------------------------------------

def _score_to_grade(score: float) -> str:
    if score >= 97:
        return "A+"
    elif score >= 93:
        return "A"
    elif score >= 90:
        return "A-"
    elif score >= 87:
        return "B+"
    elif score >= 83:
        return "B"
    elif score >= 80:
        return "B-"
    elif score >= 77:
        return "C+"
    elif score >= 73:
        return "C"
    elif score >= 70:
        return "C-"
    elif score >= 67:
        return "D+"
    elif score >= 63:
        return "D"
    elif score >= 60:
        return "D-"
    else:
        return "F"


# -----------------------------------------------------------------------
# Subsystem scorers
# -----------------------------------------------------------------------

def _score_bios() -> SubsystemScore:
    """Score BIOS health across all systems."""
    ss = SubsystemScore(name="bios", weight=WEIGHTS["bios"])
    try:
        from engines.bios_manager import audit_all
        result = audit_all()
        if isinstance(result, dict):
            systems = result.get("systems", [])
            if systems:
                scores = [s.get("health_score", 0) for s in systems if isinstance(s, dict)]
                ss.score = sum(scores) / len(scores) if scores else 0
                low = [s for s in systems if isinstance(s, dict) and s.get("health_score", 100) < 70]
                for s in low[:5]:
                    ss.issues.append(f"BIOS health low for {s.get('system', '?')}: {s.get('health_score', 0)}%")
                    ss.suggestions.append(f"Add missing BIOS files for {s.get('system', '?')}")
                ss.details = f"{len(systems)} systems audited, avg {ss.score:.0f}%"
            else:
                ss.score = 50
                ss.details = "No BIOS data available"
        else:
            ss.score = 50
    except Exception as e:
        ss.score = 50
        ss.details = f"BIOS audit unavailable: {e}"
    return ss


def _score_roms() -> SubsystemScore:
    """Score ROM collection health."""
    ss = SubsystemScore(name="roms", weight=WEIGHTS["roms"])
    try:
        from engines.rom_completion import completion_overview
        overview = completion_overview()
        if overview.get("per_system"):
            pcts = [s.get("completion_pct", 0) for s in overview["per_system"]]
            ss.score = sum(pcts) / len(pcts) if pcts else 0
            low = [s for s in overview["per_system"] if s.get("completion_pct", 100) < 50]
            for s in low[:5]:
                ss.issues.append(f"ROM completion low for {s.get('system', '?')}: {s.get('completion_pct', 0)}%")
                ss.suggestions.append(f"Add missing ROMs for {s.get('system', '?')} ({s.get('missing', 0)} missing)")
            ss.details = f"{overview.get('systems_tracked', 0)} systems, overall {overview.get('overall_pct', 0):.1f}%"
        else:
            ss.score = 70
            ss.details = "No completion data — run completion checks first"
    except Exception:
        ss.score = 70
        ss.details = "ROM completion data unavailable"
    return ss


def _score_media() -> SubsystemScore:
    """Score media coverage."""
    ss = SubsystemScore(name="media", weight=WEIGHTS["media"])
    try:
        from engines.media_audit import get_cached_summary
        summary = get_cached_summary()
        if summary:
            coverage = summary.get("overall_coverage_pct", 50)
            ss.score = coverage
            low_systems = summary.get("lowest_coverage_systems", [])
            for s in low_systems[:5]:
                ss.issues.append(f"Media coverage low: {s}")
            ss.details = f"Overall media coverage: {coverage:.0f}%"
        else:
            ss.score = 60
            ss.details = "No media audit data"
    except Exception:
        ss.score = 60
        ss.details = "Media audit unavailable"
    return ss


def _score_emulators() -> SubsystemScore:
    """Score emulator health."""
    ss = SubsystemScore(name="emulators", weight=WEIGHTS["emulators"])
    try:
        from engines.emulator_health import check_all_emulators
        result = check_all_emulators()
        if isinstance(result, dict):
            total = result.get("total", 0)
            healthy = result.get("healthy", 0)
            ss.score = (healthy / total * 100) if total > 0 else 50
            unhealthy = result.get("unhealthy", [])
            for u in unhealthy[:5]:
                emu_name = u if isinstance(u, str) else u.get("name", "?")
                ss.issues.append(f"Emulator unhealthy: {emu_name}")
                ss.suggestions.append(f"Fix or reinstall {emu_name}")
            ss.details = f"{healthy}/{total} emulators healthy"
        else:
            ss.score = 70
    except Exception:
        ss.score = 70
        ss.details = "Emulator health check unavailable"
    return ss


def _score_config() -> SubsystemScore:
    """Score configuration health."""
    ss = SubsystemScore(name="config", weight=WEIGHTS["config"])
    try:
        from engines.rl_config_validator import validate_all
        result = validate_all()
        if isinstance(result, dict):
            errors = result.get("errors", 0)
            warnings = result.get("warnings", 0)
            total = result.get("total_checked", 1)
            error_rate = errors / max(total, 1)
            ss.score = max(0, 100 - (error_rate * 100) - (warnings * 2))
            if errors > 0:
                ss.issues.append(f"{errors} config errors found")
                ss.suggestions.append("Fix configuration errors in RocketLauncher settings")
            ss.details = f"{errors} errors, {warnings} warnings in {total} configs"
        else:
            ss.score = 75
    except Exception:
        ss.score = 75
        ss.details = "Config validation unavailable"
    return ss


def _score_integrity() -> SubsystemScore:
    """Score data integrity."""
    ss = SubsystemScore(name="integrity", weight=WEIGHTS["integrity"])
    try:
        from engines.integrity_checker import get_last_report
        report = get_last_report()
        if report:
            passed = report.get("passed", 0)
            failed = report.get("failed", 0)
            total = passed + failed
            ss.score = (passed / total * 100) if total > 0 else 50
            if failed > 0:
                ss.issues.append(f"{failed} integrity checks failed")
                ss.suggestions.append("Run integrity repair to fix failed checks")
            ss.details = f"{passed}/{total} checks passed"
        else:
            ss.score = 75
            ss.details = "No integrity data — run an integrity check"
    except Exception:
        ss.score = 75
        ss.details = "Integrity checker unavailable"
    return ss


def _score_completion() -> SubsystemScore:
    """Score collection completeness goals."""
    ss = SubsystemScore(name="completion", weight=WEIGHTS["completion"])
    try:
        from engines.rom_completion import check_goal_progress
        progress = check_goal_progress()
        if progress.get("goals"):
            achieved = progress.get("achieved", 0)
            total = progress.get("total", 1)
            ss.score = (achieved / total * 100) if total > 0 else 50
            for g in progress["goals"]:
                if not g.get("achieved"):
                    ss.issues.append(f"Goal not met: {g.get('system', '?')} at {g.get('current_pct', 0):.0f}% / {g.get('target_pct', 100):.0f}%")
            ss.details = f"{achieved}/{total} goals achieved"
        else:
            ss.score = 50
            ss.details = "No collection goals set"
            ss.suggestions.append("Set collection goals with set_collection_goal")
    except Exception:
        ss.score = 50
        ss.details = "Goal tracking unavailable"
    return ss


def _score_scheduler() -> SubsystemScore:
    """Score automation/scheduler health."""
    ss = SubsystemScore(name="scheduler", weight=WEIGHTS["scheduler"])
    try:
        from engines.scheduler import get_scheduler_status
        status = get_scheduler_status()
        if isinstance(status, dict):
            total = status.get("total_tasks", 0)
            enabled = status.get("enabled_tasks", 0)
            due = status.get("due_tasks", 0)
            if total == 0:
                ss.score = 40
                ss.suggestions.append("Install default scheduled tasks")
            else:
                ss.score = (enabled / total * 100) if total > 0 else 50
                if due > 0:
                    ss.issues.append(f"{due} tasks are overdue")
                    ss.suggestions.append("Run overdue maintenance tasks")
            ss.details = f"{enabled}/{total} tasks enabled, {due} due"
        else:
            ss.score = 50
    except Exception:
        ss.score = 50
        ss.details = "Scheduler unavailable"
    return ss


# -----------------------------------------------------------------------
# Narrative generation
# -----------------------------------------------------------------------

def _generate_narrative(report: HealthReport) -> str:
    """Generate a human-readable health narrative."""
    score = report.overall_score
    grade = report.grade

    if score >= 90:
        opening = f"Your HyperSpin setup is in excellent condition ({grade}, {score:.0f}/100)."
    elif score >= 75:
        opening = f"Your HyperSpin setup is in good shape ({grade}, {score:.0f}/100) with room for improvement."
    elif score >= 60:
        opening = f"Your HyperSpin setup needs attention ({grade}, {score:.0f}/100). Several areas require fixes."
    else:
        opening = f"Your HyperSpin setup has significant issues ({grade}, {score:.0f}/100). Immediate action recommended."

    # Find strongest and weakest
    sorted_subs = sorted(report.subsystems, key=lambda s: s.score, reverse=True)
    strongest = sorted_subs[0] if sorted_subs else None
    weakest = sorted_subs[-1] if sorted_subs else None

    parts = [opening]

    if strongest:
        parts.append(f"Strongest area: {strongest.name} ({strongest.score:.0f}%).")
    if weakest and weakest.score < 80:
        parts.append(f"Weakest area: {weakest.name} ({weakest.score:.0f}%).")

    issue_count = len(report.top_issues)
    if issue_count > 0:
        parts.append(f"Found {issue_count} issue{'s' if issue_count != 1 else ''} to address.")
    else:
        parts.append("No critical issues detected.")

    return " ".join(parts)


# -----------------------------------------------------------------------
# Trend analysis
# -----------------------------------------------------------------------

def _get_trend(current_score: float) -> str:
    """Determine trend by comparing to previous snapshot."""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT overall_score FROM health_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "first_check"
        prev = row[0]
        diff = current_score - prev
        if diff > 3:
            return "improving"
        elif diff < -3:
            return "declining"
        return "stable"
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Main API
# -----------------------------------------------------------------------

def calculate_health_score(save_snapshot: bool = True) -> Dict[str, Any]:
    """Calculate the full ecosystem health score.

    Args:
        save_snapshot: Save result to history DB

    Returns:
        Complete health report
    """
    scorers = [
        _score_bios,
        _score_roms,
        _score_media,
        _score_emulators,
        _score_config,
        _score_integrity,
        _score_completion,
        _score_scheduler,
    ]

    subsystems: List[SubsystemScore] = []
    for scorer in scorers:
        try:
            ss = scorer()
            ss.weighted_score = round(ss.score * ss.weight, 2)
            subsystems.append(ss)
        except Exception as e:
            logger.warning("Scorer %s failed: %s", scorer.__name__, e)

    overall = sum(ss.weighted_score for ss in subsystems)
    overall = round(max(0, min(100, overall)), 1)

    # Collect top issues and suggestions
    all_issues = []
    all_suggestions = []
    for ss in subsystems:
        all_issues.extend(ss.issues)
        all_suggestions.extend(ss.suggestions)

    trend = _get_trend(overall)

    report = HealthReport(
        overall_score=overall,
        grade=_score_to_grade(overall),
        subsystems=subsystems,
        top_issues=all_issues[:10],
        top_suggestions=all_suggestions[:10],
        timestamp=datetime.now(timezone.utc).isoformat(),
        trend=trend,
    )

    report.narrative = _generate_narrative(report)

    if save_snapshot:
        _save_snapshot(report)

    return report.to_dict()


def _save_snapshot(report: HealthReport):
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT INTO health_snapshots
            (timestamp, overall_score, grade, subsystems_json, narrative, trend)
            VALUES (?,?,?,?,?,?)
        """, (report.timestamp, report.overall_score, report.grade,
              json.dumps([s.to_dict() for s in report.subsystems]),
              report.narrative, report.trend))
        conn.commit()
    finally:
        conn.close()


def get_health_history(limit: int = 20) -> Dict[str, Any]:
    """Get health score history."""
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT timestamp, overall_score, grade, trend FROM health_snapshots ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return {
            "history": [
                {"timestamp": r[0], "score": r[1], "grade": r[2], "trend": r[3]}
                for r in rows
            ],
            "count": len(rows),
        }
    finally:
        conn.close()


def get_subsystem_breakdown() -> Dict[str, Any]:
    """Get the latest subsystem score breakdown."""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT subsystems_json, overall_score, grade, timestamp FROM health_snapshots ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {"error": "No health data — run calculate_health_score first"}
        subs = json.loads(row[0])
        return {
            "overall_score": row[1],
            "grade": row[2],
            "timestamp": row[3],
            "subsystems": subs,
            "weights": WEIGHTS,
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
        print("  python health_score.py check")
        print("  python health_score.py history")
        print("  python health_score.py breakdown")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "check":
        result = calculate_health_score()
        print(json.dumps(result, indent=2))

    elif cmd == "history":
        result = get_health_history()
        print(json.dumps(result, indent=2))

    elif cmd == "breakdown":
        result = get_subsystem_breakdown()
        print(json.dumps(result, indent=2))
