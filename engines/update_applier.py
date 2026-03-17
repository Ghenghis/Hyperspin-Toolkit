"""M11 — Unified emulator update applier.

Combines release_checker (check/download) with update_manager (snapshot/apply/test/commit/rollback)
into a single high-level workflow for CLI, MCP, and dashboard consumption.
"""
from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("update_applier")

# Re-export known repos for convenience
from engines.release_checker import EMULATOR_REPOS


def list_tracked_emulators() -> list[dict[str, Any]]:
    """Return the list of tracked emulators with install status."""
    emu_root = Path(cfg_get("paths.emulators_root", ""))
    result = []
    for name, info in EMULATOR_REPOS.items():
        local_dir = emu_root / info["local_dir"]
        result.append({
            "emulator": name,
            "installed": local_dir.exists(),
            "local_dir": str(local_dir),
            "github": f"{info['owner']}/{info['repo']}",
        })
    return result


def check_updates(emulator_name: str | None = None) -> dict[str, Any]:
    """Check one or all emulators for available updates.

    Returns a summary dict with per-emulator update info.
    """
    from engines.release_checker import check_all_emulators, check_single_emulator

    if emulator_name:
        result = check_single_emulator(emulator_name)
        if result is None:
            return {"error": f"Unknown or unreachable emulator: {emulator_name}"}
        return {
            "checked": 1,
            "updates_available": 1 if result.get("update_available") else 0,
            "emulators": [result],
        }

    results = check_all_emulators()
    updates = [r for r in results if r.get("update_available")]
    return {
        "checked": len(results),
        "updates_available": len(updates),
        "emulators": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def download_emulator_update(emulator_name: str, target_dir: str | None = None) -> dict[str, Any]:
    """Download the latest release asset for an emulator.

    Returns dict with download path, size, and status.
    """
    from engines.release_checker import check_single_emulator

    info = check_single_emulator(emulator_name)
    if not info or not info.get("download_url"):
        return {"error": f"No download URL available for {emulator_name}", "emulator": emulator_name}

    dl_dir = Path(target_dir) if target_dir else Path(cfg_get("paths.output_root", "")) / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    url = info["download_url"]
    filename = url.split("/")[-1]
    filepath = dl_dir / filename

    try:
        import httpx
        log.info("Downloading %s from %s", filename, url)
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        size = filepath.stat().st_size
        log.info("Downloaded %s (%d bytes)", filepath, size)
        audit("update_downloaded", emulator_name, {"file": str(filepath), "size": size})

        return {
            "emulator": emulator_name,
            "status": "downloaded",
            "file": str(filepath),
            "filename": filename,
            "size_bytes": size,
            "latest_tag": info.get("latest_tag"),
            "download_url": url,
        }
    except Exception as exc:
        log.error("Download failed for %s: %s", emulator_name, exc)
        if filepath.exists():
            filepath.unlink()
        return {"emulator": emulator_name, "status": "download_failed", "error": str(exc)}


def apply_update(
    emulator_name: str,
    update_source: str,
    method: str = "auto",
    test_cmd: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Full update pipeline: snapshot → apply → test → commit/rollback.

    Args:
        emulator_name: Name of the emulator to update.
        update_source: Path to downloaded update file or directory.
        method: 'auto' (detect from extension), 'copy', 'extract', 'script'.
        test_cmd: Optional command to verify the update worked.
        dry_run: If True, only create snapshot and report what would happen.

    Returns:
        Pipeline result dict with status and details.
    """
    from engines.update_manager import UpdatePipeline
    from engines.release_checker import detect_local_version

    emu_root = Path(cfg_get("paths.emulators_root", ""))
    info = EMULATOR_REPOS.get(emulator_name)
    if not info:
        return {"error": f"Unknown emulator: {emulator_name}", "emulator": emulator_name}

    target_path = emu_root / info["local_dir"]
    source_path = Path(update_source)

    if not source_path.exists():
        return {"error": f"Update source not found: {update_source}", "emulator": emulator_name}

    # Auto-detect method
    if method == "auto":
        ext = source_path.suffix.lower()
        if ext in (".zip", ".7z"):
            method = "extract"
        elif ext in (".exe", ".bat", ".cmd"):
            method = "script"
        else:
            method = "copy"

    old_version = detect_local_version(emulator_name) or "unknown"

    result: dict[str, Any] = {
        "emulator": emulator_name,
        "target": str(target_path),
        "source": str(source_path),
        "method": method,
        "old_version": old_version,
        "steps": [],
    }

    pipeline = UpdatePipeline(emulator_name, target_path)

    # Step 1: Register
    try:
        uid = pipeline.register(old_version=old_version, notes=f"Source: {source_path.name}")
        result["update_id"] = uid
        result["steps"].append({"step": "register", "status": "ok", "id": uid})
    except Exception as exc:
        result["steps"].append({"step": "register", "status": "error", "error": str(exc)})
        result["status"] = "register_failed"
        return result

    # Step 2: Snapshot
    try:
        snap = pipeline.snapshot()
        result["snapshot"] = str(snap)
        result["steps"].append({"step": "snapshot", "status": "ok", "path": str(snap)})
    except Exception as exc:
        result["steps"].append({"step": "snapshot", "status": "error", "error": str(exc)})
        result["status"] = "snapshot_failed"
        return result

    if dry_run:
        result["status"] = "dry_run"
        result["steps"].append({"step": "dry_run", "status": "ok", "message": "No changes made"})
        return result

    # Step 3: Apply
    try:
        apply_result = pipeline.apply(source_path, method=method)
        result["steps"].append({"step": "apply", "status": apply_result.get("status", "unknown")})
        if apply_result.get("status") not in ("applied", "extracted"):
            result["status"] = "apply_failed"
            return result
    except Exception as exc:
        result["steps"].append({"step": "apply", "status": "error", "error": str(exc)})
        result["status"] = "apply_failed"
        # Rollback
        try:
            pipeline.rollback()
            result["steps"].append({"step": "rollback", "status": "ok"})
        except Exception:
            pass
        return result

    # Step 4: Test
    try:
        test_result = pipeline.test(test_cmd=test_cmd)
        passed = test_result.get("test_passed", False)
        result["steps"].append({"step": "test", "status": "passed" if passed else "failed"})

        if not passed:
            # Rollback on test failure
            try:
                pipeline.rollback()
                result["steps"].append({"step": "rollback", "status": "ok"})
            except Exception as rb_exc:
                result["steps"].append({"step": "rollback", "status": "error", "error": str(rb_exc)})
            result["status"] = "test_failed_rolled_back"
            return result
    except Exception as exc:
        result["steps"].append({"step": "test", "status": "error", "error": str(exc)})

    # Step 5: Commit
    try:
        pipeline.commit()
        result["steps"].append({"step": "commit", "status": "ok"})
    except Exception as exc:
        result["steps"].append({"step": "commit", "status": "error", "error": str(exc)})

    new_version = detect_local_version(emulator_name) or "unknown"
    result["new_version"] = new_version
    result["status"] = "committed"

    audit("update_applied", emulator_name, {
        "old": old_version, "new": new_version, "source": str(source_path)
    })

    return result


def rollback_update(update_id: int) -> dict[str, Any]:
    """Rollback a previously applied update by its database ID."""
    rows = db.execute("SELECT * FROM update_history WHERE id=?", (update_id,))
    if not rows:
        return {"error": f"Update ID {update_id} not found"}

    row = rows[0]
    snapshot_path = row.get("snapshot_path")
    if not snapshot_path or not Path(snapshot_path).exists():
        return {"error": f"No snapshot available for update {update_id}"}

    from engines.backup import restore_from_backup

    target = row.get("target", "")
    try:
        result = restore_from_backup(snapshot_path, target)
        db.execute(
            "UPDATE update_history SET status='rolled_back', rolled_back_at=datetime('now') WHERE id=?",
            (update_id,)
        )
        audit("update_rolled_back", row.get("program_name", ""), {"id": update_id})
        return {
            "status": "rolled_back",
            "update_id": update_id,
            "program": row.get("program_name"),
            "restored_files": result.get("restored", 0),
        }
    except Exception as exc:
        return {"error": str(exc), "update_id": update_id}


def get_update_status() -> dict[str, Any]:
    """Get a summary of the update system: pending queue + recent history."""
    from engines.update_manager import get_update_queue, get_update_history
    queue = get_update_queue()
    history = get_update_history(limit=20)
    return {
        "pending": len(queue),
        "queue": queue,
        "history_count": len(history),
        "history": history,
    }
