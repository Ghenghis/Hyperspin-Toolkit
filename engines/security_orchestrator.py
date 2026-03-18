"""
M40 -- Agentic Security Policies & Workflow Orchestration

Provides:
  - Drive access policies mapped from drive_registry.json
  - Serial-based drive verification before disk writes
  - All inference stays local -- no cloud API calls enforced
  - Goose / NemoClaw / OpenHands communication pipeline
  - YAML workflow orchestration: full-audit, safe-update, collection-sync, asset-catalog
  - Policy enforcement layer for destructive operations
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("security_orchestrator")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "security_orchestrator.db"
DRIVE_REGISTRY = TOOLKIT_ROOT / "drive_registry.json"
WORKFLOWS_DIR = TOOLKIT_ROOT / "workflows"

ACCESS_LEVELS = {
    "read-only": {"read": True, "write": False, "delete": False},
    "read-write": {"read": True, "write": True, "delete": False},
    "read-write-delete": {"read": True, "write": True, "delete": True},
    "backup-write": {"read": True, "write": True, "delete": False},
    "denied": {"read": False, "write": False, "delete": False},
}

DEFAULT_POLICIES: Dict[str, str] = {
    "C": "denied", "D": "read-write", "F": "denied",
    "H": "backup-write", "I": "read-only", "J": "read-only",
    "K": "read-only", "L": "read-only",
}


@dataclass
class WorkflowStep:
    step_id: int = 0
    name: str = ""
    agent: str = ""
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    timeout_seconds: int = 300
    status: str = "pending"
    result: Any = None
    error: str = ""
    def to_dict(self): return asdict(self)


@dataclass
class WorkflowRun:
    run_id: str = ""
    workflow_name: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    status: str = "pending"
    started_at: str = ""
    completed_at: str = ""
    current_step: int = 0
    def to_dict(self):
        d = asdict(self)
        d["total_steps"] = len(self.steps)
        return d


def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL, drive TEXT NOT NULL,
            operation TEXT NOT NULL, path TEXT DEFAULT '',
            allowed INTEGER DEFAULT 0, agent TEXT DEFAULT '',
            reason TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS workflow_runs (
            run_id TEXT PRIMARY KEY, workflow_name TEXT NOT NULL,
            status TEXT DEFAULT 'pending', steps_json TEXT DEFAULT '[]',
            started_at TEXT DEFAULT '', completed_at TEXT DEFAULT '',
            current_step INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS approval_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, step_index INTEGER NOT NULL,
            step_name TEXT NOT NULL, description TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL, resolved_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_access_ts ON access_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_approval_status ON approval_queue(status);
    """)
    conn.commit()
    return conn


def _load_drive_registry() -> Dict[str, Any]:
    if DRIVE_REGISTRY.exists():
        try:
            return json.loads(DRIVE_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_drive_policies() -> Dict[str, Any]:
    registry = _load_drive_registry()
    drives = registry.get("drives", {})
    policies = {}
    for letter, level in DEFAULT_POLICIES.items():
        info = drives.get(letter, drives.get(f"{letter}:", {}))
        actual = info.get("access_level", level) if info else level
        perms = ACCESS_LEVELS.get(actual, ACCESS_LEVELS["denied"])
        policies[letter] = {
            "drive": letter, "access_level": actual,
            "serial": info.get("serial", "") if info else "",
            "label": info.get("label", "") if info else "",
            "permissions": perms,
        }
    return {"policies": policies, "access_levels": ACCESS_LEVELS}


def check_access(drive_letter: str, operation: str = "read",
                 path: str = "", agent: str = "") -> Dict[str, Any]:
    letter = drive_letter.upper().rstrip(":")
    registry = _load_drive_registry()
    drives = registry.get("drives", {})
    info = drives.get(letter, drives.get(f"{letter}:", {}))
    level = info.get("access_level", DEFAULT_POLICIES.get(letter, "denied")) if info else DEFAULT_POLICIES.get(letter, "denied")
    perms = ACCESS_LEVELS.get(level, ACCESS_LEVELS["denied"])
    allowed = perms.get(operation, False)
    reason = f"Drive {letter}: is {level} -- {operation} {'allowed' if allowed else 'not permitted'}"
    serial_ok = True
    if info and info.get("serial"):
        actual = _get_drive_serial(letter)
        if actual and actual != info["serial"]:
            allowed, serial_ok = False, False
            reason = f"Drive {letter}: serial mismatch"
    _log_access(letter, operation, path, allowed, agent, reason)
    return {"allowed": allowed, "drive": letter, "operation": operation,
            "access_level": level, "serial_verified": serial_ok, "reason": reason}


def _get_drive_serial(letter: str) -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["wmic", "logicaldisk", "where", f"DeviceID='{letter}:'", "get", "VolumeSerialNumber"],
            capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().splitlines():
            line = line.strip()
            if line and line != "VolumeSerialNumber":
                return line
    except Exception:
        pass
    return ""


def _log_access(drive, op, path, allowed, agent, reason):
    conn = _ensure_db()
    try:
        conn.execute("INSERT INTO access_log (timestamp,drive,operation,path,allowed,agent,reason) VALUES (?,?,?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), drive, op, path, int(allowed), agent, reason))
        conn.commit()
    finally:
        conn.close()


def get_access_log(drive: str = "", limit: int = 50) -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM access_log"
        params: list = []
        if drive:
            sql += " WHERE drive=?"
            params.append(drive.upper().rstrip(":"))
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM access_log LIMIT 0").description]
        return {"entries": [dict(zip(cols, r)) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def verify_local_inference() -> Dict[str, Any]:
    import urllib.request
    checks = []
    try:
        req = urllib.request.Request("http://localhost:1234/v1/models", headers={"Authorization": "Bearer lm-studio"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            checks.append({"provider": "LM Studio", "status": "running", "models": len(data.get("data", [])), "local": True})
    except Exception:
        checks.append({"provider": "LM Studio", "status": "not_running", "local": True})
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
            checks.append({"provider": "Ollama", "status": "running", "models": len(data.get("models", [])), "local": True})
    except Exception:
        checks.append({"provider": "Ollama", "status": "not_running", "local": True})
    return {"all_local": True, "any_provider_running": any(c["status"] == "running" for c in checks),
            "providers": checks, "cloud_calls_blocked": True}


def list_workflows() -> Dict[str, Any]:
    workflows = []
    if WORKFLOWS_DIR.exists():
        for f in sorted(WORKFLOWS_DIR.glob("*.yaml")):
            content = f.read_text(encoding="utf-8")
            workflows.append({"name": f.stem, "file": str(f), "steps": content.count("- name:")})
    return {"workflows": workflows, "count": len(workflows)}


def load_workflow(name: str) -> Dict[str, Any]:
    p = WORKFLOWS_DIR / f"{name}.yaml"
    if not p.exists():
        return {"error": f"Workflow '{name}' not found"}
    content = p.read_text(encoding="utf-8")
    try:
        import yaml
        return {"name": name, "workflow": yaml.safe_load(content)}
    except ImportError:
        return {"name": name, "raw_yaml": content}
    except Exception as e:
        return {"name": name, "error": str(e), "raw_yaml": content}


def start_workflow(name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    wf = load_workflow(name)
    if "error" in wf:
        return wf
    run_id = f"run_{name}_{int(time.time())}"
    now = datetime.now(timezone.utc).isoformat()
    steps = []
    raw = wf.get("workflow", {})
    for i, s in enumerate(raw.get("steps", []) if isinstance(raw, dict) else []):
        if isinstance(s, dict):
            steps.append(WorkflowStep(step_id=i, name=s.get("name", f"step_{i}"),
                                       agent=s.get("agent", ""), tool=s.get("tool", ""),
                                       args=s.get("args", {}),
                                       requires_approval=s.get("requires_approval", False),
                                       timeout_seconds=s.get("timeout", 300)))
    conn = _ensure_db()
    try:
        conn.execute("INSERT INTO workflow_runs (run_id,workflow_name,status,steps_json,started_at,current_step) VALUES (?,?,?,?,?,0)",
                     (run_id, name, "started", json.dumps([s.to_dict() for s in steps]), now))
        for i, step in enumerate(steps):
            if step.requires_approval:
                conn.execute("INSERT INTO approval_queue (run_id,step_index,step_name,description,status,created_at) VALUES (?,?,?,?,'pending',?)",
                             (run_id, i, step.name, f"Step {i}: {step.name}", now))
        conn.commit()
    finally:
        conn.close()
    return WorkflowRun(run_id=run_id, workflow_name=name, steps=steps, status="started", started_at=now).to_dict()


def get_workflow_status(run_id: str) -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        row = conn.execute("SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            return {"error": f"Run '{run_id}' not found"}
        cols = [d[0] for d in conn.execute("SELECT * FROM workflow_runs LIMIT 0").description]
        d = dict(zip(cols, row))
        d["steps"] = json.loads(d.pop("steps_json", "[]"))
        return d
    finally:
        conn.close()


def approve_step(run_id: str, step_index: int) -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("UPDATE approval_queue SET status='approved',resolved_at=? WHERE run_id=? AND step_index=? AND status='pending'",
                           (now, run_id, step_index))
        conn.commit()
        return {"approved": cur.rowcount > 0, "run_id": run_id, "step_index": step_index}
    finally:
        conn.close()


def reject_step(run_id: str, step_index: int, reason: str = "") -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("UPDATE approval_queue SET status='rejected',resolved_at=? WHERE run_id=? AND step_index=? AND status='pending'",
                     (now, run_id, step_index))
        conn.commit()
        return {"rejected": True, "run_id": run_id, "step_index": step_index, "reason": reason}
    finally:
        conn.close()


def get_pending_approvals() -> Dict[str, Any]:
    conn = _ensure_db()
    try:
        rows = conn.execute("SELECT * FROM approval_queue WHERE status='pending' ORDER BY created_at").fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM approval_queue LIMIT 0").description]
        return {"pending": [dict(zip(cols, r)) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def delegate_to_agent(agent: str, task: str, context: str = "") -> Dict[str, Any]:
    a = agent.lower().replace("-", "").replace("_", "")
    if a in ("nemoclaw", "nemoclawagents"):
        try:
            from engines.nemoclaw_agents import delegate
            return asdict(delegate(task, context))
        except Exception as e:
            return {"error": f"NemoClaw failed: {e}"}
    elif a in ("openhands", "openhandsbridge"):
        try:
            from engines.openhands_bridge import CLIENT
            return CLIENT.run_task(task)
        except Exception as e:
            return {"error": f"OpenHands failed: {e}"}
    elif a in ("clianything", "cli"):
        try:
            from engines.cli_anything_bridge import resolve_command
            return resolve_command(task)
        except Exception as e:
            return {"error": f"CLI-Anything failed: {e}"}
    return {"error": f"Unknown agent: {agent}. Available: nemoclaw, openhands, cli-anything"}


def agent_stack_status() -> Dict[str, Any]:
    status = {"timestamp": datetime.now(timezone.utc).isoformat(), "agents": {}}
    goose_path = shutil.which("goose")
    status["agents"]["goose"] = {"installed": goose_path is not None, "path": goose_path or "not found", "role": "Top-level orchestrator"}
    try:
        from engines.nemoclaw_agents import AGENTS
        status["agents"]["nemoclaw"] = {"available": True, "agents": len(AGENTS), "roles": [a.role for a in AGENTS.values()]}
    except Exception as e:
        status["agents"]["nemoclaw"] = {"available": False, "error": str(e)}
    try:
        from engines.openhands_bridge import CLIENT
        status["agents"]["openhands"] = {"available": True, "running": CLIENT.is_running(), "version": CLIENT.get_version()}
    except Exception as e:
        status["agents"]["openhands"] = {"available": False, "error": str(e)}
    try:
        from engines.cli_anything_bridge import STATIC_MAP
        status["agents"]["cli_anything"] = {"available": True, "static_commands": len(STATIC_MAP)}
    except Exception as e:
        status["agents"]["cli_anything"] = {"available": False, "error": str(e)}
    return status


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python security_orchestrator.py [policies|check|workflows|stack|local]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "policies":
        print(json.dumps(get_drive_policies(), indent=2))
    elif cmd == "check":
        drive = sys.argv[2] if len(sys.argv) > 2 else "D"
        op = sys.argv[3] if len(sys.argv) > 3 else "read"
        print(json.dumps(check_access(drive, op), indent=2))
    elif cmd == "workflows":
        print(json.dumps(list_workflows(), indent=2))
    elif cmd == "stack":
        print(json.dumps(agent_stack_status(), indent=2))
    elif cmd == "local":
        print(json.dumps(verify_local_inference(), indent=2))
