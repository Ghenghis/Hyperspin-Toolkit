"""
M61 -- Scheduler, Task Automation & Notification System

Provides:
  - Scheduled task definitions (periodic audits, backups, health checks)
  - Cron-like scheduling with configurable intervals
  - Task execution engine with logging and error handling
  - Notification system (Windows toast, log-based, in-app)
  - Maintenance cycles (night mode, pre-session, post-update)
  - Task history and status tracking in SQLite
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("scheduler")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "scheduler.db"
SCHEDULE_CONFIG = TOOLKIT_ROOT / "config" / "schedules.json"


# -----------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskInterval(str, Enum):
    MANUAL = "manual"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_STARTUP = "on_startup"
    ON_IDLE = "on_idle"


class NotifyLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class ScheduledTask:
    """Definition of a scheduled task."""
    task_id: str
    name: str
    description: str = ""
    interval: str = "daily"
    enabled: bool = True
    engine: str = ""           # e.g. "rom_audit", "self_healer"
    action: str = ""           # e.g. "full_scan", "quick_check"
    parameters: Dict[str, Any] = field(default_factory=dict)
    last_run: str = ""
    next_run: str = ""
    last_status: str = ""
    last_duration_sec: float = 0
    run_count: int = 0
    fail_count: int = 0
    notify_on_failure: bool = True
    notify_on_success: bool = False
    category: str = "general"  # audit, backup, health, cleanup, update

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskRun:
    """Record of a single task execution."""
    run_id: int = 0
    task_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    status: str = "pending"
    duration_sec: float = 0
    result_summary: str = ""
    error_message: str = ""
    items_processed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Notification:
    """A notification entry."""
    notif_id: int = 0
    timestamp: str = ""
    level: str = "info"
    title: str = ""
    message: str = ""
    source: str = ""           # task_id or engine name
    read: bool = False
    action_url: str = ""       # optional deep link

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    """Create/open the scheduler SQLite database."""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            interval TEXT DEFAULT 'daily',
            enabled INTEGER DEFAULT 1,
            engine TEXT,
            action TEXT,
            parameters TEXT DEFAULT '{}',
            last_run TEXT,
            next_run TEXT,
            last_status TEXT,
            last_duration_sec REAL DEFAULT 0,
            run_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            notify_on_failure INTEGER DEFAULT 1,
            notify_on_success INTEGER DEFAULT 0,
            category TEXT DEFAULT 'general'
        );

        CREATE TABLE IF NOT EXISTS task_runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            status TEXT DEFAULT 'pending',
            duration_sec REAL DEFAULT 0,
            result_summary TEXT,
            error_message TEXT,
            items_processed INTEGER DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES scheduled_tasks(task_id)
        );

        CREATE TABLE IF NOT EXISTS notifications (
            notif_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT DEFAULT 'info',
            title TEXT NOT NULL,
            message TEXT,
            source TEXT,
            read INTEGER DEFAULT 0,
            action_url TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_runs_task ON task_runs(task_id);
        CREATE INDEX IF NOT EXISTS idx_runs_status ON task_runs(status);
        CREATE INDEX IF NOT EXISTS idx_notif_read ON notifications(read);
        CREATE INDEX IF NOT EXISTS idx_notif_level ON notifications(level);
    """)
    conn.commit()
    return conn


# -----------------------------------------------------------------------
# Task CRUD
# -----------------------------------------------------------------------

def create_task(task: ScheduledTask) -> ScheduledTask:
    """Create or update a scheduled task."""
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO scheduled_tasks
            (task_id, name, description, interval, enabled, engine, action,
             parameters, last_run, next_run, last_status, last_duration_sec,
             run_count, fail_count, notify_on_failure, notify_on_success, category)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            task.task_id, task.name, task.description, task.interval,
            int(task.enabled), task.engine, task.action,
            json.dumps(task.parameters), task.last_run,
            task.next_run or _compute_next_run(task.interval),
            task.last_status, task.last_duration_sec,
            task.run_count, task.fail_count,
            int(task.notify_on_failure), int(task.notify_on_success),
            task.category,
        ))
        conn.commit()
        logger.info("Task created/updated: %s", task.task_id)
    finally:
        conn.close()
    return task


def get_task(task_id: str) -> Optional[ScheduledTask]:
    """Get a scheduled task by ID."""
    conn = _ensure_db()
    try:
        row = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE task_id=?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return _row_to_task(row, conn)
    finally:
        conn.close()


def list_tasks(category: Optional[str] = None,
               enabled_only: bool = False) -> List[ScheduledTask]:
    """List all scheduled tasks."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM scheduled_tasks WHERE 1=1"
        params: list = []
        if category:
            sql += " AND category=?"
            params.append(category)
        if enabled_only:
            sql += " AND enabled=1"
        sql += " ORDER BY category, name"
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_task(r, conn) for r in rows]
    finally:
        conn.close()


def delete_task(task_id: str) -> bool:
    """Delete a scheduled task and its run history."""
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM task_runs WHERE task_id=?", (task_id,))
        result = conn.execute("DELETE FROM scheduled_tasks WHERE task_id=?", (task_id,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def toggle_task(task_id: str, enabled: bool) -> bool:
    """Enable or disable a task."""
    conn = _ensure_db()
    try:
        result = conn.execute(
            "UPDATE scheduled_tasks SET enabled=? WHERE task_id=?",
            (int(enabled), task_id)
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def _row_to_task(row, conn) -> ScheduledTask:
    cols = [d[0] for d in conn.execute("SELECT * FROM scheduled_tasks LIMIT 0").description]
    d = dict(zip(cols, row))
    d["enabled"] = bool(d.get("enabled", 0))
    d["notify_on_failure"] = bool(d.get("notify_on_failure", 1))
    d["notify_on_success"] = bool(d.get("notify_on_success", 0))
    d["parameters"] = json.loads(d.get("parameters", "{}"))
    return ScheduledTask(**d)


# -----------------------------------------------------------------------
# Task execution
# -----------------------------------------------------------------------

# Registry of executable task actions
_TASK_REGISTRY: Dict[str, Callable] = {}


def register_task_action(engine: str, action: str, func: Callable) -> None:
    """Register a callable for a given engine+action pair."""
    key = f"{engine}.{action}"
    _TASK_REGISTRY[key] = func
    logger.debug("Registered task action: %s", key)


def _resolve_action(engine: str, action: str) -> Optional[Callable]:
    """Resolve a task action to a callable."""
    key = f"{engine}.{action}"
    if key in _TASK_REGISTRY:
        return _TASK_REGISTRY[key]

    # Dynamic import fallback
    try:
        mod = __import__(f"engines.{engine}", fromlist=[action])
        func = getattr(mod, action, None)
        if func and callable(func):
            _TASK_REGISTRY[key] = func
            return func
    except (ImportError, AttributeError):
        pass

    return None


def run_task(task_id: str, force: bool = False) -> TaskRun:
    """Execute a scheduled task immediately.

    Args:
        task_id: ID of the task to run
        force: Run even if disabled or not yet due

    Returns:
        TaskRun record with execution results
    """
    task = get_task(task_id)
    if not task:
        return TaskRun(task_id=task_id, status="failed",
                       error_message=f"Task not found: {task_id}")

    if not task.enabled and not force:
        return TaskRun(task_id=task_id, status="skipped",
                       error_message="Task is disabled")

    run = TaskRun(
        task_id=task_id,
        started_at=datetime.now(timezone.utc).isoformat(),
        status="running",
    )

    # Record run start
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "INSERT INTO task_runs (task_id, started_at, status) VALUES (?,?,?)",
            (run.task_id, run.started_at, run.status)
        )
        conn.commit()
        run.run_id = cur.lastrowid
    finally:
        conn.close()

    # Execute
    start_time = time.time()
    try:
        action_func = _resolve_action(task.engine, task.action)
        if action_func is None:
            raise RuntimeError(f"No handler for {task.engine}.{task.action}")

        result = action_func(**task.parameters)
        run.status = "completed"

        if isinstance(result, dict):
            run.result_summary = json.dumps(result, default=str)[:5000]
            run.items_processed = result.get("count", result.get("total", 0))
        elif isinstance(result, str):
            run.result_summary = result[:5000]

    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)[:2000]
        logger.error("Task %s failed: %s", task_id, e)

    run.finished_at = datetime.now(timezone.utc).isoformat()
    run.duration_sec = round(time.time() - start_time, 2)

    # Update run record
    conn = _ensure_db()
    try:
        conn.execute("""
            UPDATE task_runs SET finished_at=?, status=?, duration_sec=?,
                   result_summary=?, error_message=?, items_processed=?
            WHERE run_id=?
        """, (run.finished_at, run.status, run.duration_sec,
              run.result_summary, run.error_message, run.items_processed,
              run.run_id))

        # Update task stats
        conn.execute("""
            UPDATE scheduled_tasks SET
                last_run=?, last_status=?, last_duration_sec=?,
                run_count = run_count + 1,
                fail_count = fail_count + CASE WHEN ?='failed' THEN 1 ELSE 0 END,
                next_run=?
            WHERE task_id=?
        """, (run.started_at, run.status, run.duration_sec,
              run.status, _compute_next_run(task.interval), task_id))
        conn.commit()
    finally:
        conn.close()

    # Notifications
    if run.status == "failed" and task.notify_on_failure:
        send_notification(
            level="error",
            title=f"Task Failed: {task.name}",
            message=run.error_message[:500],
            source=task_id,
        )
    elif run.status == "completed" and task.notify_on_success:
        send_notification(
            level="info",
            title=f"Task Completed: {task.name}",
            message=f"Processed {run.items_processed} items in {run.duration_sec}s",
            source=task_id,
        )

    return run


def get_due_tasks() -> List[ScheduledTask]:
    """Get all enabled tasks that are due to run."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT * FROM scheduled_tasks WHERE enabled=1 AND (next_run <= ? OR next_run IS NULL OR next_run = '')",
            (now,)
        ).fetchall()
        return [_row_to_task(r, conn) for r in rows]
    finally:
        conn.close()


def run_due_tasks() -> List[TaskRun]:
    """Run all tasks that are currently due."""
    due = get_due_tasks()
    results = []
    for task in due:
        logger.info("Running due task: %s", task.task_id)
        run = run_task(task.task_id)
        results.append(run)
    return results


def get_task_history(task_id: str, limit: int = 20) -> List[TaskRun]:
    """Get execution history for a task."""
    conn = _ensure_db()
    try:
        rows = conn.execute(
            "SELECT * FROM task_runs WHERE task_id=? ORDER BY started_at DESC LIMIT ?",
            (task_id, limit)
        ).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM task_runs LIMIT 0").description]
        return [TaskRun(**dict(zip(cols, r))) for r in rows]
    finally:
        conn.close()


# -----------------------------------------------------------------------
# Scheduling helpers
# -----------------------------------------------------------------------

def _compute_next_run(interval: str, from_time: Optional[datetime] = None) -> str:
    """Compute the next run time based on interval."""
    now = from_time or datetime.now(timezone.utc)
    deltas = {
        "hourly": timedelta(hours=1),
        "daily": timedelta(days=1),
        "weekly": timedelta(weeks=1),
        "monthly": timedelta(days=30),
    }
    delta = deltas.get(interval)
    if delta:
        return (now + delta).isoformat()
    return ""  # manual, on_startup, on_idle — no automatic next_run


# -----------------------------------------------------------------------
# Notification system
# -----------------------------------------------------------------------

def send_notification(level: str = "info", title: str = "",
                      message: str = "", source: str = "",
                      action_url: str = "") -> int:
    """Send a notification (stored + optional Windows toast)."""
    conn = _ensure_db()
    try:
        cur = conn.execute(
            "INSERT INTO notifications (timestamp, level, title, message, source, action_url) VALUES (?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(), level, title, message, source, action_url)
        )
        conn.commit()
        notif_id = cur.lastrowid
    finally:
        conn.close()

    # Windows toast notification for warnings+
    if level in ("warning", "error", "critical"):
        _send_toast(title, message)

    logger.info("Notification [%s]: %s — %s", level, title, message[:100])
    return notif_id


def get_notifications(unread_only: bool = False, level: Optional[str] = None,
                      limit: int = 50) -> List[Notification]:
    """Get notifications from the database."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM notifications WHERE 1=1"
        params: list = []
        if unread_only:
            sql += " AND read=0"
        if level:
            sql += " AND level=?"
            params.append(level)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM notifications LIMIT 0").description]
        result = []
        for r in rows:
            d = dict(zip(cols, r))
            d["read"] = bool(d.get("read", 0))
            result.append(Notification(**d))
        return result
    finally:
        conn.close()


def mark_notification_read(notif_id: int) -> bool:
    """Mark a notification as read."""
    conn = _ensure_db()
    try:
        result = conn.execute("UPDATE notifications SET read=1 WHERE notif_id=?", (notif_id,))
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def mark_all_read() -> int:
    """Mark all notifications as read."""
    conn = _ensure_db()
    try:
        result = conn.execute("UPDATE notifications SET read=1 WHERE read=0")
        conn.commit()
        return result.rowcount
    finally:
        conn.close()


def clear_old_notifications(days: int = 30) -> int:
    """Delete notifications older than N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    conn = _ensure_db()
    try:
        result = conn.execute("DELETE FROM notifications WHERE timestamp < ?", (cutoff,))
        conn.commit()
        return result.rowcount
    finally:
        conn.close()


def _send_toast(title: str, message: str) -> None:
    """Send a Windows toast notification (best-effort)."""
    try:
        ps_script = f"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType = WindowsRuntime] | Out-Null
$template = @"
<toast>
  <visual>
    <binding template="ToastGeneric">
      <text>{title}</text>
      <text>{message[:200]}</text>
    </binding>
  </visual>
</toast>
"@
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($template)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("KINHANK Toolkit").Show($toast)
"""
        subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as e:
        logger.debug("Toast notification failed: %s", e)


# -----------------------------------------------------------------------
# Maintenance cycles (pre-built task sets)
# -----------------------------------------------------------------------

DEFAULT_TASKS: List[ScheduledTask] = [
    ScheduledTask(
        task_id="audit_rom_daily",
        name="Daily ROM Audit",
        description="Quick ROM collection audit checking for new/missing/changed files",
        interval="daily",
        engine="rom_audit",
        action="quick_audit",
        category="audit",
        notify_on_failure=True,
    ),
    ScheduledTask(
        task_id="audit_media_weekly",
        name="Weekly Media Audit",
        description="Full media asset audit (images, videos, wheels) across all systems",
        interval="weekly",
        engine="media_audit",
        action="audit_all_systems",
        category="audit",
        notify_on_failure=True,
    ),
    ScheduledTask(
        task_id="health_check_daily",
        name="Daily Health Check",
        description="Quick system health check — drives, emulators, configs",
        interval="daily",
        engine="self_healer",
        action="scan_issues",
        category="health",
        notify_on_failure=True,
    ),
    ScheduledTask(
        task_id="drive_health_weekly",
        name="Weekly Drive Health",
        description="Check SMART status and disk space across all gaming drives",
        interval="weekly",
        engine="drive_index",
        action="check_health",
        category="health",
        notify_on_failure=True,
        notify_on_success=True,
    ),
    ScheduledTask(
        task_id="cleanup_temp_weekly",
        name="Weekly Temp Cleanup",
        description="Remove stale temp files, empty logs, and cache entries",
        interval="weekly",
        engine="self_healer",
        action="cleanup_temp",
        category="cleanup",
        notify_on_success=True,
    ),
    ScheduledTask(
        task_id="backup_config_daily",
        name="Daily Config Backup",
        description="Incremental backup of all configuration files",
        interval="daily",
        engine="backup",
        action="backup_configs",
        category="backup",
    ),
    ScheduledTask(
        task_id="pre_session_check",
        name="Pre-Session Health Check",
        description="Quick validation before gaming — verify critical paths and emulators",
        interval="on_startup",
        engine="self_healer",
        action="quick_check",
        category="health",
    ),
]


def install_default_tasks() -> int:
    """Install all default scheduled tasks (skip if already exist)."""
    installed = 0
    for task in DEFAULT_TASKS:
        existing = get_task(task.task_id)
        if not existing:
            create_task(task)
            installed += 1
    logger.info("Installed %d default tasks (%d already existed)",
                installed, len(DEFAULT_TASKS) - installed)
    return installed


def run_maintenance_cycle(cycle: str = "night") -> Dict[str, Any]:
    """Run a predefined maintenance cycle.

    Cycles:
      - night: Full audit + cleanup + backup (for idle/overnight)
      - pre_session: Quick health check before gaming
      - post_update: Verify everything after an emulator/ROM update
    """
    cycle_tasks = {
        "night": ["audit_rom_daily", "audit_media_weekly", "health_check_daily",
                   "cleanup_temp_weekly", "backup_config_daily"],
        "pre_session": ["pre_session_check"],
        "post_update": ["health_check_daily", "audit_rom_daily"],
    }

    task_ids = cycle_tasks.get(cycle, [])
    if not task_ids:
        return {"error": f"Unknown cycle: {cycle}", "valid_cycles": list(cycle_tasks.keys())}

    results = []
    for tid in task_ids:
        run = run_task(tid, force=True)
        results.append(run.to_dict())

    completed = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "cycle": cycle,
        "tasks_run": len(results),
        "completed": completed,
        "failed": failed,
        "results": results,
    }


# -----------------------------------------------------------------------
# Scheduler status
# -----------------------------------------------------------------------

def get_scheduler_status() -> Dict[str, Any]:
    """Get overall scheduler status."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM scheduled_tasks").fetchone()[0]
        enabled = conn.execute("SELECT COUNT(*) FROM scheduled_tasks WHERE enabled=1").fetchone()[0]
        due = len(get_due_tasks())

        recent_runs = conn.execute(
            "SELECT status, COUNT(*) FROM task_runs WHERE started_at > datetime('now', '-24 hours') GROUP BY status"
        ).fetchall()

        unread = conn.execute("SELECT COUNT(*) FROM notifications WHERE read=0").fetchone()[0]

        return {
            "total_tasks": total,
            "enabled_tasks": enabled,
            "due_tasks": due,
            "recent_24h": {r[0]: r[1] for r in recent_runs},
            "unread_notifications": unread,
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
        print("  python scheduler.py install    — Install default tasks")
        print("  python scheduler.py list       — List all tasks")
        print("  python scheduler.py run <id>   — Run a task by ID")
        print("  python scheduler.py due        — Run all due tasks")
        print("  python scheduler.py cycle <name> — Run maintenance cycle")
        print("  python scheduler.py status     — Show scheduler status")
        print("  python scheduler.py notify     — Show notifications")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "install":
        n = install_default_tasks()
        print(f"Installed {n} default tasks")

    elif cmd == "list":
        tasks = list_tasks()
        for t in tasks:
            status = "ON" if t.enabled else "OFF"
            print(f"  [{status}] {t.task_id}: {t.name} ({t.interval}) — last: {t.last_status or 'never'}")

    elif cmd == "run":
        tid = sys.argv[2] if len(sys.argv) > 2 else ""
        if not tid:
            print("Usage: python scheduler.py run <task_id>")
        else:
            result = run_task(tid, force=True)
            print(f"  Status: {result.status} ({result.duration_sec}s)")
            if result.error_message:
                print(f"  Error: {result.error_message}")

    elif cmd == "due":
        results = run_due_tasks()
        print(f"Ran {len(results)} due tasks")
        for r in results:
            print(f"  {r.task_id}: {r.status}")

    elif cmd == "cycle":
        name = sys.argv[2] if len(sys.argv) > 2 else "night"
        result = run_maintenance_cycle(name)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "status":
        status = get_scheduler_status()
        print(json.dumps(status, indent=2))

    elif cmd == "notify":
        notifs = get_notifications(limit=10)
        for n in notifs:
            icon = "*" if not n.read else " "
            print(f"  {icon} [{n.level}] {n.title}: {n.message[:80]}")
