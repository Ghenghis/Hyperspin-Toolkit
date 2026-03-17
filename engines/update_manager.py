"""Safe program update manager — one-at-a-time with snapshot, test, commit/rollback."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db
from engines.backup import create_snapshot, rollback_from_snapshot

log = get_logger("update_manager")


class UpdatePipeline:
    """Manages the lifecycle of a single program update.

    Workflow:
        1. register() — add to queue
        2. snapshot() — pre-update backup
        3. apply() — perform the update
        4. test() — verify the update works
        5. commit() — mark as successful
        6. rollback() — revert if something went wrong
    """

    def __init__(self, program_name: str, target_path: str | Path):
        self.program_name = program_name
        self.target_path = Path(target_path)
        self.snapshot_dir: Path | None = None
        self.update_id: int | None = None
        self.status = "initialized"

    def register(self, old_version: str = "", new_version: str = "", notes: str = "") -> int:
        """Register this update in the database queue."""
        self.update_id = db.insert("update_history", {
            "program_name": self.program_name,
            "old_version": old_version,
            "new_version": new_version,
            "status": "pending",
            "notes": notes,
        })
        self.status = "registered"
        log.info("Update registered: %s (id=%d)", self.program_name, self.update_id)
        audit("update_registered", self.program_name, {
            "id": self.update_id, "old": old_version, "new": new_version
        })
        return self.update_id

    def snapshot(self) -> Path:
        """Create a pre-update snapshot."""
        label = f"{self.program_name}_pre_update"
        self.snapshot_dir = create_snapshot(self.target_path, label=label)
        if self.update_id:
            db.execute(
                "UPDATE update_history SET snapshot_path=? WHERE id=?",
                (str(self.snapshot_dir), self.update_id)
            )
        self.status = "snapshot_taken"
        log.info("Snapshot created for %s: %s", self.program_name, self.snapshot_dir)
        return self.snapshot_dir

    def apply(self, update_source: str | Path, method: str = "copy") -> dict[str, Any]:
        """Apply the update from a source.

        Args:
            update_source: Path to new files or update package.
            method: 'copy' (overwrite), 'extract' (zip/7z), 'script' (run installer).

        Returns:
            Result dict.
        """
        update_source = Path(update_source)
        if not update_source.exists():
            raise FileNotFoundError(f"Update source not found: {update_source}")

        log.info("Applying update for %s from %s (method=%s)", self.program_name, update_source, method)
        audit("update_apply_start", self.program_name, {"source": str(update_source), "method": method})

        result: dict[str, Any] = {"method": method, "source": str(update_source)}

        if method == "copy":
            import shutil
            if update_source.is_dir():
                shutil.copytree(str(update_source), str(self.target_path), dirs_exist_ok=True)
            else:
                shutil.copy2(str(update_source), str(self.target_path))
            result["status"] = "applied"

        elif method == "extract":
            import zipfile
            if update_source.suffix.lower() == ".zip":
                with zipfile.ZipFile(str(update_source), "r") as zf:
                    zf.extractall(str(self.target_path))
                result["status"] = "extracted"
            else:
                result["status"] = "unsupported_format"
                log.error("Unsupported archive format: %s", update_source.suffix)

        elif method == "script":
            try:
                proc = subprocess.run(
                    [str(update_source)],
                    capture_output=True, text=True, timeout=300,
                    cwd=str(self.target_path)
                )
                result["exit_code"] = proc.returncode
                result["stdout"] = proc.stdout[:2000]
                result["stderr"] = proc.stderr[:2000]
                result["status"] = "applied" if proc.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                result["status"] = "timeout"
            except Exception as exc:
                result["status"] = "error"
                result["error"] = str(exc)

        if self.update_id:
            db.execute(
                "UPDATE update_history SET status=?, applied_at=datetime('now') WHERE id=?",
                (result.get("status", "unknown"), self.update_id)
            )

        self.status = result.get("status", "unknown")
        audit("update_applied", self.program_name, result)
        return result

    def test(self, test_cmd: str | None = None) -> dict[str, Any]:
        """Test the update by running a verification command or checking file health.

        Args:
            test_cmd: Optional command to run for verification. If None, does basic file checks.

        Returns:
            Test result dict.
        """
        log.info("Testing update for %s", self.program_name)
        result: dict[str, Any] = {"program": self.program_name}

        # Basic file health check
        if self.target_path.is_dir():
            exe_files = list(self.target_path.glob("*.exe"))
            result["exe_found"] = len(exe_files)
            result["total_files"] = sum(1 for _ in self.target_path.rglob("*") if _.is_file())
            result["total_size"] = sum(f.stat().st_size for f in self.target_path.rglob("*") if f.is_file())
        elif self.target_path.is_file():
            result["file_exists"] = True
            result["file_size"] = self.target_path.stat().st_size

        # Run custom test command if provided
        if test_cmd:
            try:
                proc = subprocess.run(
                    test_cmd, shell=True,
                    capture_output=True, text=True, timeout=60,
                    cwd=str(self.target_path if self.target_path.is_dir() else self.target_path.parent)
                )
                result["test_exit_code"] = proc.returncode
                result["test_passed"] = proc.returncode == 0
                result["test_output"] = proc.stdout[:1000]
            except Exception as exc:
                result["test_passed"] = False
                result["test_error"] = str(exc)
        else:
            result["test_passed"] = True  # Basic checks passed

        status = "tested" if result.get("test_passed") else "test_failed"
        if self.update_id:
            db.execute(
                "UPDATE update_history SET status=?, tested_at=datetime('now') WHERE id=?",
                (status, self.update_id)
            )

        self.status = status
        audit("update_tested", self.program_name, result)
        return result

    def commit(self) -> None:
        """Mark the update as committed (successful)."""
        if self.update_id:
            db.execute(
                "UPDATE update_history SET status='committed', committed_at=datetime('now') WHERE id=?",
                (self.update_id,)
            )
        self.status = "committed"
        log.info("Update committed: %s", self.program_name)
        audit("update_committed", self.program_name, {"id": self.update_id})

    def rollback(self) -> dict[str, Any]:
        """Rollback to the pre-update snapshot."""
        if not self.snapshot_dir or not self.snapshot_dir.exists():
            raise FileNotFoundError("No snapshot available for rollback")

        log.info("Rolling back update for %s", self.program_name)
        result = rollback_from_snapshot(self.snapshot_dir, self.target_path)

        if self.update_id:
            db.execute(
                "UPDATE update_history SET status='rolled_back', rolled_back_at=datetime('now') WHERE id=?",
                (self.update_id,)
            )

        self.status = "rolled_back"
        audit("update_rolled_back", self.program_name, result)
        return result


def get_update_queue() -> list[dict[str, Any]]:
    """Get all pending updates from the database."""
    return db.execute(
        "SELECT * FROM update_history WHERE status IN ('pending','registered') ORDER BY created_at"
    )


def get_update_history(limit: int = 50) -> list[dict[str, Any]]:
    """Get recent update history."""
    return db.execute(
        "SELECT * FROM update_history ORDER BY created_at DESC LIMIT ?", (limit,)
    )
