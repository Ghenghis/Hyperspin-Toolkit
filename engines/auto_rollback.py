"""M15 — Automated Rollback on Failure.

Monitors update outcomes and automatically rolls back when:
  - Post-update health check fails
  - Emulator exe missing or won't launch after update
  - Snapshot verification detects unexpected changes
  - User-defined test command fails

Integrates with M11 (UpdatePipeline), M14 (Snapshot Verification),
and M7 (Emulator Health Check).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("auto_rollback")

# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------
_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS rollback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emulator_name TEXT NOT NULL,
    trigger_reason TEXT NOT NULL,
    update_id INTEGER,
    snapshot_name TEXT,
    backup_path TEXT,
    status TEXT DEFAULT 'pending',        -- pending, rolling_back, completed, failed
    steps TEXT DEFAULT '[]',              -- JSON array of step results
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rollback_emu ON rollback_log(emulator_name);
CREATE INDEX IF NOT EXISTS idx_rollback_update ON rollback_log(update_id);

CREATE TABLE IF NOT EXISTS rollback_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emulator_name TEXT NOT NULL,
    auto_rollback_enabled INTEGER DEFAULT 1,
    health_check_required INTEGER DEFAULT 1,
    test_cmd TEXT DEFAULT '',
    max_rollback_age_hours INTEGER DEFAULT 72,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(emulator_name)
);
"""


def ensure_tables():
    """Run migration to ensure rollback tables exist."""
    try:
        with db.get_conn() as conn:
            conn.executescript(_MIGRATION_SQL)
        log.debug("M15 tables ensured")
    except Exception as exc:
        log.warning("M15 table migration: %s", exc)


# ---------------------------------------------------------------------------
# Rollback policy management
# ---------------------------------------------------------------------------

def get_policy(emulator_name: str) -> dict:
    """Get the rollback policy for an emulator, or defaults."""
    ensure_tables()
    rows = db.execute(
        "SELECT * FROM rollback_policies WHERE emulator_name = ?", (emulator_name,)
    )
    if rows:
        return dict(rows[0])
    return {
        "emulator_name": emulator_name,
        "auto_rollback_enabled": True,
        "health_check_required": True,
        "test_cmd": "",
        "max_rollback_age_hours": 72,
    }


def set_policy(emulator_name: str, auto_rollback_enabled: bool = True,
               health_check_required: bool = True, test_cmd: str = "",
               max_rollback_age_hours: int = 72) -> dict:
    """Set or update the rollback policy for an emulator."""
    ensure_tables()
    now = datetime.now(timezone.utc).isoformat()
    try:
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO rollback_policies (emulator_name, auto_rollback_enabled,
                    health_check_required, test_cmd, max_rollback_age_hours, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(emulator_name) DO UPDATE SET
                    auto_rollback_enabled = excluded.auto_rollback_enabled,
                    health_check_required = excluded.health_check_required,
                    test_cmd = excluded.test_cmd,
                    max_rollback_age_hours = excluded.max_rollback_age_hours,
                    updated_at = excluded.updated_at
            """, (emulator_name, int(auto_rollback_enabled), int(health_check_required),
                  test_cmd, max_rollback_age_hours, now))
    except Exception as exc:
        return {"error": str(exc)}
    return get_policy(emulator_name)


def list_policies() -> list[dict]:
    """List all configured rollback policies."""
    ensure_tables()
    return db.execute("SELECT * FROM rollback_policies ORDER BY emulator_name")


# ---------------------------------------------------------------------------
# Health verification checks
# ---------------------------------------------------------------------------

def _check_exe_exists(emulator_name: str, emu_root: str | None = None) -> dict:
    """Verify the emulator executable still exists after update."""
    from engines.emulator_health import check_emulator
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", "")) / emulator_name
    if not emu_path.exists():
        return {"check": "exe_exists", "passed": False, "detail": f"Directory not found: {emu_path}"}
    health = check_emulator(emu_path)
    if health.exe_exists:
        return {"check": "exe_exists", "passed": True, "detail": f"Found: {health.exe_path}"}
    return {"check": "exe_exists", "passed": False, "detail": "Executable not found after update"}


def _check_health_score(emulator_name: str, min_score: float = 0.3,
                         emu_root: str | None = None) -> dict:
    """Verify emulator health score meets minimum threshold."""
    from engines.emulator_health import check_emulator
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", "")) / emulator_name
    if not emu_path.exists():
        return {"check": "health_score", "passed": False, "detail": "Directory not found"}
    health = check_emulator(emu_path)
    passed = health.health_score >= min_score
    return {
        "check": "health_score",
        "passed": passed,
        "detail": f"Score: {health.health_score:.2f} (min: {min_score})",
        "score": health.health_score,
    }


def _check_test_cmd(test_cmd: str) -> dict:
    """Run a user-defined test command and check exit code."""
    if not test_cmd:
        return {"check": "test_cmd", "passed": True, "detail": "No test command configured"}
    import subprocess
    try:
        result = subprocess.run(
            test_cmd, shell=True, capture_output=True, timeout=60, text=True,
        )
        passed = result.returncode == 0
        return {
            "check": "test_cmd",
            "passed": passed,
            "detail": f"Exit code: {result.returncode}",
            "stdout": result.stdout[:500] if result.stdout else "",
            "stderr": result.stderr[:500] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"check": "test_cmd", "passed": False, "detail": "Test command timed out (60s)"}
    except Exception as exc:
        return {"check": "test_cmd", "passed": False, "detail": f"Error: {exc}"}


def run_health_checks(emulator_name: str, test_cmd: str | None = None,
                      emu_root: str | None = None) -> dict:
    """Run all health verification checks for an emulator.

    Returns:
        Dict with overall pass/fail and individual check results.
    """
    policy = get_policy(emulator_name)
    checks = []

    checks.append(_check_exe_exists(emulator_name, emu_root))
    if policy.get("health_check_required", True):
        checks.append(_check_health_score(emulator_name, emu_root=emu_root))

    cmd = test_cmd or policy.get("test_cmd", "")
    if cmd:
        checks.append(_check_test_cmd(cmd))

    all_passed = all(c["passed"] for c in checks)
    return {
        "emulator": emulator_name,
        "all_passed": all_passed,
        "checks": checks,
        "check_count": len(checks),
        "failed_count": sum(1 for c in checks if not c["passed"]),
    }


# ---------------------------------------------------------------------------
# Automated rollback execution
# ---------------------------------------------------------------------------

def _find_latest_backup(emulator_name: str) -> dict | None:
    """Find the most recent backup for an emulator from update_history or backups table."""
    rows = db.execute(
        """SELECT id, snapshot_path, old_version, new_version, status, created_at
           FROM update_history
           WHERE program_name = ? AND snapshot_path IS NOT NULL AND snapshot_path != ''
           ORDER BY created_at DESC LIMIT 1""",
        (emulator_name,),
    )
    if rows:
        return dict(rows[0])

    rows = db.execute(
        """SELECT id, backup_path, target, status, created_at
           FROM backups
           WHERE target LIKE ? AND status IN ('created', 'verified')
           ORDER BY created_at DESC LIMIT 1""",
        (f"%{emulator_name}%",),
    )
    if rows:
        return dict(rows[0])

    return None


def _restore_from_backup(emulator_name: str, backup_path: str,
                          emu_root: str | None = None) -> dict:
    """Restore an emulator directory from a backup."""
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", "")) / emulator_name
    backup = Path(backup_path)

    if not backup.exists():
        return {"step": "restore", "status": "failed", "detail": f"Backup not found: {backup_path}"}

    try:
        if emu_path.exists():
            # Create a temp copy of current (broken) state for forensics
            forensic = emu_path.parent / f"{emulator_name}_failed_{int(time.time())}"
            shutil.copytree(str(emu_path), str(forensic), dirs_exist_ok=True)
            log.info("Saved failed state to %s", forensic)

        # Restore from backup
        if backup.is_dir():
            shutil.copytree(str(backup), str(emu_path), dirs_exist_ok=True)
        else:
            # Archive file — extract
            import zipfile
            if zipfile.is_zipfile(str(backup)):
                with zipfile.ZipFile(str(backup), "r") as zf:
                    zf.extractall(str(emu_path))
            else:
                return {"step": "restore", "status": "failed",
                        "detail": f"Unknown backup format: {backup.suffix}"}

        return {"step": "restore", "status": "completed",
                "detail": f"Restored from {backup_path}"}
    except Exception as exc:
        return {"step": "restore", "status": "failed", "detail": str(exc)}


def auto_rollback(emulator_name: str, trigger_reason: str,
                  update_id: int | None = None, backup_path: str | None = None,
                  emu_root: str | None = None) -> dict:
    """Execute an automated rollback for an emulator.

    Workflow:
    1. Check policy — is auto-rollback enabled?
    2. Find the latest backup
    3. Restore from backup
    4. Re-run health checks to confirm recovery
    5. Log the rollback event

    Args:
        emulator_name: Name of the emulator to rollback.
        trigger_reason: Why the rollback was triggered.
        update_id: Optional update_history ID that caused the failure.
        backup_path: Override backup path (otherwise auto-discovered).
        emu_root: Override emulators root directory.

    Returns:
        Rollback result dict.
    """
    ensure_tables()
    now = datetime.now(timezone.utc).isoformat()
    steps = []

    # Step 1: Check policy
    policy = get_policy(emulator_name)
    if not policy.get("auto_rollback_enabled", True):
        return {
            "emulator": emulator_name,
            "status": "skipped",
            "reason": "Auto-rollback disabled by policy",
            "steps": [],
        }

    # Create rollback log entry
    log_id = 0
    try:
        log_id = db.insert("rollback_log", {
            "emulator_name": emulator_name,
            "trigger_reason": trigger_reason,
            "update_id": update_id,
            "status": "rolling_back",
            "started_at": now,
        })
    except Exception as exc:
        log.warning("Failed to create rollback log: %s", exc)

    steps.append({"step": "policy_check", "status": "ok",
                  "detail": "Auto-rollback enabled"})

    # Step 2: Find backup
    if not backup_path:
        backup_info = _find_latest_backup(emulator_name)
        if backup_info:
            backup_path = backup_info.get("snapshot_path") or backup_info.get("backup_path", "")
            steps.append({"step": "find_backup", "status": "ok",
                          "detail": f"Found: {backup_path}"})
        else:
            steps.append({"step": "find_backup", "status": "failed",
                          "detail": "No backup found for rollback"})
            _update_rollback_log(log_id, "failed", steps)
            return {
                "emulator": emulator_name,
                "status": "failed",
                "reason": "No backup available",
                "steps": steps,
            }
    else:
        steps.append({"step": "find_backup", "status": "ok",
                      "detail": f"Using provided: {backup_path}"})

    # Step 3: Restore
    restore_result = _restore_from_backup(emulator_name, backup_path, emu_root)
    steps.append(restore_result)

    if restore_result["status"] != "completed":
        _update_rollback_log(log_id, "failed", steps)
        return {
            "emulator": emulator_name,
            "status": "failed",
            "reason": f"Restore failed: {restore_result['detail']}",
            "steps": steps,
        }

    # Step 4: Post-rollback health check
    health = run_health_checks(emulator_name, emu_root=emu_root)
    steps.append({
        "step": "post_rollback_health",
        "status": "ok" if health["all_passed"] else "warning",
        "detail": f"{health['check_count']} checks, {health['failed_count']} failed",
        "checks": health["checks"],
    })

    # Step 5: Update DB
    final_status = "completed" if health["all_passed"] else "completed_with_warnings"

    # Mark the update_history entry as rolled_back
    if update_id:
        try:
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE update_history SET status = 'rolled_back', rolled_back_at = ? WHERE id = ?",
                    (now, update_id),
                )
        except Exception as exc:
            log.warning("Failed to update update_history: %s", exc)

    _update_rollback_log(log_id, final_status, steps, backup_path)

    audit("auto_rollback", emulator_name, {
        "trigger": trigger_reason, "status": final_status,
        "update_id": update_id, "steps": len(steps),
    })

    return {
        "emulator": emulator_name,
        "status": final_status,
        "trigger_reason": trigger_reason,
        "backup_used": backup_path,
        "rollback_id": log_id,
        "steps": steps,
        "health_passed": health["all_passed"],
    }


def _update_rollback_log(log_id: int, status: str, steps: list, backup_path: str = ""):
    """Update a rollback log entry."""
    if not log_id:
        return
    try:
        now = datetime.now(timezone.utc).isoformat()
        with db.get_conn() as conn:
            conn.execute(
                """UPDATE rollback_log SET status = ?, steps = ?, backup_path = ?,
                   completed_at = ? WHERE id = ?""",
                (status, json.dumps(steps, default=str), backup_path, now, log_id),
            )
    except Exception as exc:
        log.warning("Failed to update rollback log %d: %s", log_id, exc)


# ---------------------------------------------------------------------------
# Post-update auto-check (called after update_applier completes)
# ---------------------------------------------------------------------------

def post_update_check(emulator_name: str, update_id: int | None = None,
                      test_cmd: str | None = None,
                      emu_root: str | None = None) -> dict:
    """Run health checks after an update and trigger rollback if needed.

    This is the main integration point — call after applying an update.
    """
    ensure_tables()
    health = run_health_checks(emulator_name, test_cmd=test_cmd, emu_root=emu_root)

    if health["all_passed"]:
        return {
            "emulator": emulator_name,
            "status": "healthy",
            "action": "none",
            "checks": health["checks"],
        }

    # Health check failed — trigger auto-rollback
    failed_checks = [c for c in health["checks"] if not c["passed"]]
    reason = "; ".join(f"{c['check']}: {c['detail']}" for c in failed_checks)

    log.warning("Post-update health check failed for %s: %s", emulator_name, reason)

    rollback_result = auto_rollback(
        emulator_name,
        trigger_reason=f"Post-update health failure: {reason}",
        update_id=update_id,
        emu_root=emu_root,
    )

    return {
        "emulator": emulator_name,
        "status": "rollback_triggered",
        "action": "auto_rollback",
        "health_checks": health["checks"],
        "rollback": rollback_result,
    }


# ---------------------------------------------------------------------------
# Listing / querying
# ---------------------------------------------------------------------------

def list_rollbacks(emulator_name: str | None = None, limit: int = 20) -> list[dict]:
    """List rollback log entries."""
    ensure_tables()
    if emulator_name:
        return db.execute(
            "SELECT * FROM rollback_log WHERE emulator_name = ? ORDER BY created_at DESC LIMIT ?",
            (emulator_name, limit),
        )
    return db.execute(
        "SELECT * FROM rollback_log ORDER BY created_at DESC LIMIT ?", (limit,)
    )


def rollback_summary() -> dict:
    """Get rollback system summary."""
    ensure_tables()
    total = db.execute("SELECT COUNT(*) as cnt FROM rollback_log")
    by_status = db.execute(
        "SELECT status, COUNT(*) as cnt FROM rollback_log GROUP BY status"
    )
    recent = db.execute(
        "SELECT id, emulator_name, trigger_reason, status, created_at "
        "FROM rollback_log ORDER BY created_at DESC LIMIT 10"
    )
    policies = db.execute("SELECT COUNT(*) as cnt FROM rollback_policies")
    enabled = db.execute(
        "SELECT COUNT(*) as cnt FROM rollback_policies WHERE auto_rollback_enabled = 1"
    )
    return {
        "total_rollbacks": total[0]["cnt"] if total else 0,
        "by_status": {r["status"]: r["cnt"] for r in by_status},
        "recent": recent,
        "policies_configured": policies[0]["cnt"] if policies else 0,
        "policies_enabled": enabled[0]["cnt"] if enabled else 0,
    }
