"""Base agent class for the agentic workflow orchestrator."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from core.logger import get_logger, audit
from core import database as db

log = get_logger("agent")


class AgentResult:
    """Container for agent task results."""

    def __init__(self, agent_name: str, task: str, success: bool, data: Any = None, error: str = ""):
        self.agent_name = agent_name
        self.task = task
        self.success = success
        self.data = data
        self.error = error
        self.timestamp = datetime.now().isoformat()
        self.duration_ms: float = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent_name,
            "task": self.task,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }


class BaseAgent(ABC):
    """Abstract base class for all toolkit agents.

    Each agent has a specific role (Auditor, Updater, Researcher, Optimizer, Reporter)
    and can execute tasks autonomously or with human-in-the-loop approval.
    """

    def __init__(self, name: str, role: str, requires_approval: bool = False):
        self.name = name
        self.role = role
        self.requires_approval = requires_approval
        self.log = get_logger(f"agent.{name}")

    @abstractmethod
    def execute(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        """Execute a task. Must be implemented by subclasses."""
        ...

    def run(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        """Run a task with logging, timing, and audit trail."""
        self.log.info("Agent %s starting task: %s", self.name, task)
        audit("agent_task_start", self.name, {"task": task, "params": params})

        start = time.time()
        try:
            result = self.execute(task, params or {})
        except Exception as exc:
            result = AgentResult(self.name, task, False, error=str(exc))
            self.log.error("Agent %s task failed: %s — %s", self.name, task, exc)

        result.duration_ms = round((time.time() - start) * 1000, 2)

        audit("agent_task_complete", self.name, result.to_dict())
        self.log.info("Agent %s completed task: %s (success=%s, %dms)",
                      self.name, task, result.success, result.duration_ms)
        return result


class AuditorAgent(BaseAgent):
    """Agent that audits the HyperSpin ecosystem."""

    def __init__(self):
        super().__init__("auditor", "Auditor", requires_approval=False)

    def execute(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        params = params or {}

        if task == "full_audit":
            from engines.auditor import run_full_audit
            data = run_full_audit()
            return AgentResult(self.name, task, True, data=data.get("summary"))

        elif task == "audit_system":
            system_name = params.get("system_name", "")
            if not system_name:
                return AgentResult(self.name, task, False, error="system_name required")
            from engines.auditor import audit_system
            data = audit_system(system_name)
            return AgentResult(self.name, task, True, data=data)

        elif task == "audit_emulators":
            from engines.auditor import audit_emulators
            data = audit_emulators()
            return AgentResult(self.name, task, True, data={"count": len(data)})

        elif task == "find_duplicates":
            system = params.get("system_name")
            from engines.auditor import find_duplicate_roms
            data = find_duplicate_roms(system)
            return AgentResult(self.name, task, True, data={"groups": len(data)})

        return AgentResult(self.name, task, False, error=f"Unknown task: {task}")


class BackupAgent(BaseAgent):
    """Agent that manages backups and recovery."""

    def __init__(self):
        super().__init__("backup", "Backup Manager", requires_approval=True)

    def execute(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        params = params or {}

        if task == "create_backup":
            source = params.get("source", "")
            label = params.get("label", "agent_backup")
            backup_type = params.get("type", "full")
            if not source:
                return AgentResult(self.name, task, False, error="source required")
            from engines.backup import create_backup
            data = create_backup(source, label=label, backup_type=backup_type)
            return AgentResult(self.name, task, True, data=data)

        elif task == "verify_backup":
            backup_dir = params.get("backup_dir", "")
            if not backup_dir:
                return AgentResult(self.name, task, False, error="backup_dir required")
            from engines.backup import verify_backup
            data = verify_backup(backup_dir)
            return AgentResult(self.name, task, True, data=data)

        elif task == "restore":
            backup_dir = params.get("backup_dir", "")
            target = params.get("target", "")
            dry_run = params.get("dry_run", True)
            if not backup_dir or not target:
                return AgentResult(self.name, task, False, error="backup_dir and target required")
            from engines.backup import restore_from_backup
            data = restore_from_backup(backup_dir, target, dry_run=dry_run)
            return AgentResult(self.name, task, True, data=data)

        return AgentResult(self.name, task, False, error=f"Unknown task: {task}")


class UpdateAgent(BaseAgent):
    """Agent that manages safe program updates."""

    def __init__(self):
        super().__init__("updater", "Update Manager", requires_approval=True)

    def execute(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        params = params or {}

        if task == "register_update":
            program = params.get("program_name", "")
            target = params.get("target_path", "")
            if not program or not target:
                return AgentResult(self.name, task, False, error="program_name and target_path required")
            from engines.update_manager import UpdatePipeline
            pipeline = UpdatePipeline(program, target)
            uid = pipeline.register(
                old_version=params.get("old_version", ""),
                new_version=params.get("new_version", ""),
                notes=params.get("notes", ""),
            )
            return AgentResult(self.name, task, True, data={"update_id": uid})

        elif task == "get_queue":
            from engines.update_manager import get_update_queue
            queue = get_update_queue()
            return AgentResult(self.name, task, True, data={"queue": queue})

        elif task == "get_history":
            from engines.update_manager import get_update_history
            history = get_update_history(params.get("limit", 50))
            return AgentResult(self.name, task, True, data={"history": history})

        return AgentResult(self.name, task, False, error=f"Unknown task: {task}")


class ResearchAgent(BaseAgent):
    """Agent that uses AI to research and analyze the collection."""

    def __init__(self):
        super().__init__("researcher", "Research Agent", requires_approval=False)

    def execute(self, task: str, params: dict[str, Any] | None = None) -> AgentResult:
        params = params or {}

        if task == "analyze_collection":
            from engines.ai_engine import get_ai
            from engines.auditor import run_full_audit
            audit_data = run_full_audit()
            ai = get_ai()
            analysis = ai.analyze_collection(audit_data.get("summary", {}))
            return AgentResult(self.name, task, True, data={"analysis": analysis})

        elif task == "identify_rom":
            filename = params.get("filename", "")
            system = params.get("system", "")
            if not filename:
                return AgentResult(self.name, task, False, error="filename required")
            from engines.ai_engine import get_ai
            ai = get_ai()
            result = ai.identify_rom(filename, system)
            return AgentResult(self.name, task, True, data={"identification": result})

        elif task == "troubleshoot":
            issue = params.get("issue", "")
            error_log = params.get("error_log", "")
            if not issue:
                return AgentResult(self.name, task, False, error="issue description required")
            from engines.ai_engine import get_ai
            ai = get_ai()
            result = ai.troubleshoot(issue, error_log)
            return AgentResult(self.name, task, True, data={"solution": result})

        elif task == "nl_query":
            question = params.get("question", "")
            if not question:
                return AgentResult(self.name, task, False, error="question required")
            from engines.ai_engine import get_nl_query
            nlq = get_nl_query()
            result = nlq.query(question)
            return AgentResult(self.name, task, True, data=result)

        return AgentResult(self.name, task, False, error=f"Unknown task: {task}")


# ---------------------------------------------------------------------------
# Agent registry
# ---------------------------------------------------------------------------

_agents: dict[str, BaseAgent] = {}


def get_agent(name: str) -> BaseAgent:
    """Get or create an agent by name."""
    if name not in _agents:
        agent_map = {
            "auditor": AuditorAgent,
            "backup": BackupAgent,
            "updater": UpdateAgent,
            "researcher": ResearchAgent,
        }
        cls = agent_map.get(name)
        if not cls:
            raise ValueError(f"Unknown agent: {name}")
        _agents[name] = cls()
    return _agents[name]


def list_agents() -> list[dict[str, str]]:
    """List all available agents."""
    return [
        {"name": "auditor", "role": "Auditor", "description": "Audits ROMs, emulators, media, configs"},
        {"name": "backup", "role": "Backup Manager", "description": "Creates and manages backups/recovery"},
        {"name": "updater", "role": "Update Manager", "description": "Safe program updates with rollback"},
        {"name": "researcher", "role": "Research Agent", "description": "AI-powered analysis and research"},
    ]
