"""Versioned, incremental backup and recovery engine."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("backup")


# ---------------------------------------------------------------------------
# Hash manifest
# ---------------------------------------------------------------------------

def build_manifest(root: Path, exclude: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Build a file hash manifest for a directory tree."""
    exclude = exclude or cfg_get("backup.exclude_patterns", [])
    manifest: dict[str, dict[str, Any]] = {}
    algo = cfg_get("audit.hash_algorithm", "sha256")

    for fpath in root.rglob("*"):
        if not fpath.is_file():
            continue
        rel = str(fpath.relative_to(root))
        if any(pat.lower() in rel.lower() for pat in exclude):
            continue
        try:
            h = hashlib.new(algo)
            with open(fpath, "rb") as fh:
                while True:
                    chunk = fh.read(1 << 20)
                    if not chunk:
                        break
                    h.update(chunk)
            manifest[rel] = {
                "hash": h.hexdigest(),
                "size": fpath.stat().st_size,
                "mtime": fpath.stat().st_mtime,
            }
        except Exception as exc:
            log.warning("Cannot hash %s: %s", fpath, exc)
            manifest[rel] = {"hash": None, "size": 0, "mtime": 0}

    return manifest


def save_manifest(manifest: dict, dest: Path) -> None:
    """Save manifest to JSON file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, default=str)


def load_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Load a previously saved manifest."""
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------

def diff_manifests(old: dict, new: dict) -> dict[str, list[str]]:
    """Compare two manifests. Returns {added, modified, deleted, unchanged}."""
    added = [k for k in new if k not in old]
    deleted = [k for k in old if k not in new]
    modified = [
        k for k in new
        if k in old and new[k].get("hash") != old[k].get("hash")
    ]
    unchanged = [
        k for k in new
        if k in old and new[k].get("hash") == old[k].get("hash")
    ]
    return {"added": added, "modified": modified, "deleted": deleted, "unchanged": unchanged}


# ---------------------------------------------------------------------------
# Backup creation
# ---------------------------------------------------------------------------

def create_backup(
    source: str | Path,
    label: str = "manual",
    backup_type: str = "full",
    incremental_base: Path | None = None,
) -> dict[str, Any]:
    """Create a versioned backup of a directory.

    Args:
        source: Directory to back up.
        label: Human-readable label for this backup.
        backup_type: 'full' or 'incremental'.
        incremental_base: Path to previous manifest for incremental backup.

    Returns:
        Summary dict with backup metadata.
    """
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    backup_root = Path(cfg_get("paths.backup_root", ""))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{label}_{backup_type}_{timestamp}"
    backup_dir = backup_root / backup_name
    backup_dir.mkdir(parents=True, exist_ok=True)

    log.info("Creating %s backup: %s → %s", backup_type, source, backup_dir)
    audit("backup_start", str(source), {"type": backup_type, "label": label})

    # Build current manifest
    current_manifest = build_manifest(source)
    manifest_path = backup_dir / "manifest.json"
    save_manifest(current_manifest, manifest_path)

    # Determine which files to back up
    if backup_type == "incremental" and incremental_base and incremental_base.exists():
        old_manifest = load_manifest(incremental_base)
        diff = diff_manifests(old_manifest, current_manifest)
        files_to_backup = diff["added"] + diff["modified"]
        log.info("Incremental: %d added, %d modified, %d deleted, %d unchanged",
                 len(diff["added"]), len(diff["modified"]),
                 len(diff["deleted"]), len(diff["unchanged"]))
    else:
        files_to_backup = list(current_manifest.keys())
        backup_type = "full"

    # Create backup archive
    compression = cfg_get("backup.compression", "zip")
    file_count = 0
    total_size = 0

    if compression == "zip":
        archive_path = backup_dir / f"{backup_name}.zip"
        with zipfile.ZipFile(str(archive_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for rel_path in files_to_backup:
                full_path = source / rel_path
                if full_path.exists():
                    zf.write(str(full_path), rel_path)
                    file_count += 1
                    total_size += full_path.stat().st_size
    elif compression == "none":
        archive_path = backup_dir / "files"
        archive_path.mkdir(exist_ok=True)
        for rel_path in files_to_backup:
            full_path = source / rel_path
            if full_path.exists():
                dest = archive_path / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(full_path), str(dest))
                file_count += 1
                total_size += full_path.stat().st_size
    else:
        archive_path = backup_dir / "files"
        archive_path.mkdir(exist_ok=True)
        for rel_path in files_to_backup:
            full_path = source / rel_path
            if full_path.exists():
                dest = archive_path / rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(full_path), str(dest))
                file_count += 1
                total_size += full_path.stat().st_size

    # Save metadata
    meta = {
        "backup_name": backup_name,
        "backup_type": backup_type,
        "source": str(source),
        "label": label,
        "timestamp": timestamp,
        "file_count": file_count,
        "total_size_bytes": total_size,
        "archive_path": str(archive_path),
        "manifest_path": str(manifest_path),
        "compression": compression,
    }
    meta_path = backup_dir / "backup_meta.json"
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, default=str)

    # Register in database
    try:
        db.insert("backups", {
            "backup_type": backup_type,
            "target": str(source),
            "backup_path": str(backup_dir),
            "size_bytes": total_size,
            "file_count": file_count,
            "hash_manifest": str(manifest_path),
            "status": "created",
        })
    except Exception as exc:
        log.warning("Failed to record backup in DB: %s", exc)

    # Verify if configured
    if cfg_get("backup.verify_after_create", True):
        verify_backup(backup_dir)

    log.info("Backup complete: %d files, %s bytes → %s", file_count, f"{total_size:,}", backup_dir)
    audit("backup_complete", str(backup_dir), meta)
    return meta


# ---------------------------------------------------------------------------
# Backup verification
# ---------------------------------------------------------------------------

def verify_backup(backup_dir: str | Path) -> dict[str, Any]:
    """Verify a backup's integrity by checking the archive against the manifest."""
    backup_dir = Path(backup_dir)
    manifest_path = backup_dir / "manifest.json"
    meta_path = backup_dir / "backup_meta.json"

    if not manifest_path.exists():
        return {"status": "error", "message": "No manifest found"}

    manifest = load_manifest(manifest_path)
    meta = {}
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)

    archive_path = meta.get("archive_path", "")
    errors: list[str] = []

    if archive_path.endswith(".zip") and Path(archive_path).exists():
        with zipfile.ZipFile(archive_path, "r") as zf:
            archived_files = set(zf.namelist())
            for rel_path in manifest:
                if rel_path not in archived_files:
                    errors.append(f"Missing from archive: {rel_path}")

    result = {
        "status": "verified" if not errors else "errors",
        "total_files": len(manifest),
        "errors": errors,
        "error_count": len(errors),
    }

    if not errors:
        log.info("Backup verified OK: %s", backup_dir)
    else:
        log.warning("Backup verification found %d errors in %s", len(errors), backup_dir)

    return result


# ---------------------------------------------------------------------------
# Recovery / Restore
# ---------------------------------------------------------------------------

def restore_from_backup(
    backup_dir: str | Path,
    target: str | Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Restore files from a backup to a target directory.

    Args:
        backup_dir: Path to the backup directory.
        target: Where to restore files.
        dry_run: If True, only report what would be restored.

    Returns:
        Summary dict.
    """
    backup_dir = Path(backup_dir)
    target = Path(target)
    meta_path = backup_dir / "backup_meta.json"

    if not meta_path.exists():
        raise FileNotFoundError(f"No backup_meta.json in {backup_dir}")

    with open(meta_path, "r", encoding="utf-8") as fh:
        meta = json.load(fh)

    archive_path = Path(meta["archive_path"])
    restored = 0
    skipped = 0

    log.info("Restoring from %s to %s (dry_run=%s)", backup_dir, target, dry_run)
    audit("restore_start", str(target), {"backup": str(backup_dir), "dry_run": dry_run})

    if str(archive_path).endswith(".zip") and archive_path.exists():
        with zipfile.ZipFile(str(archive_path), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                dest = target / info.filename
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    zf.extract(info, str(target))
                restored += 1
    elif archive_path.is_dir():
        for fpath in archive_path.rglob("*"):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(archive_path)
            dest = target / rel
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(fpath), str(dest))
            restored += 1

    result = {
        "backup_dir": str(backup_dir),
        "target": str(target),
        "restored": restored,
        "dry_run": dry_run,
    }

    log.info("Restore complete: %d files %s", restored, "(dry run)" if dry_run else "")
    audit("restore_complete", str(target), result)
    return result


# ---------------------------------------------------------------------------
# Snapshot (lightweight pre-update backup)
# ---------------------------------------------------------------------------

def create_snapshot(target: str | Path, label: str = "pre_update") -> Path:
    """Create a quick snapshot of a directory before an update."""
    target = Path(target)
    backup_root = Path(cfg_get("paths.backup_root", ""))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = backup_root / "snapshots" / f"{label}_{timestamp}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    log.info("Creating snapshot: %s → %s", target, snap_dir)

    if target.is_file():
        shutil.copy2(str(target), str(snap_dir / target.name))
    elif target.is_dir():
        shutil.copytree(str(target), str(snap_dir / target.name), dirs_exist_ok=True)

    # Save manifest
    if target.is_dir():
        manifest = build_manifest(target)
        save_manifest(manifest, snap_dir / "manifest.json")

    audit("snapshot_created", str(target), {"snapshot": str(snap_dir)})
    return snap_dir


def rollback_from_snapshot(snapshot_dir: str | Path, target: str | Path) -> dict[str, Any]:
    """Rollback a target to a previous snapshot state."""
    snapshot_dir = Path(snapshot_dir)
    target = Path(target)

    if not snapshot_dir.exists():
        raise FileNotFoundError(f"Snapshot not found: {snapshot_dir}")

    log.info("Rolling back %s from snapshot %s", target, snapshot_dir)
    audit("rollback_start", str(target), {"snapshot": str(snapshot_dir)})

    restored = 0
    for item in snapshot_dir.iterdir():
        if item.name == "manifest.json":
            continue
        dest = target if item.name == target.name else target / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.copytree(str(item), str(dest))
        elif item.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(dest))
        restored += 1

    result = {"snapshot": str(snapshot_dir), "target": str(target), "items_restored": restored}
    log.info("Rollback complete: %d items restored", restored)
    audit("rollback_complete", str(target), result)
    return result
