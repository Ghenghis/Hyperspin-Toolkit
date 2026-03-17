"""Space Optimizer — finds duplicates, redundant files, and recovery opportunities.

Critical for 60 GB free on 12 TB drive.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

from core.logger import get_logger, audit
from core.config import get

log = get_logger("space_optimizer")


def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def _hash_file(filepath: Path, algorithm: str = "md5", chunk_size: int = 65536) -> str:
    """Fast file hashing. Uses MD5 for speed in dedup (not security)."""
    h = hashlib.new(algorithm)
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as exc:
        log.warning("Cannot hash %s: %s", filepath, exc)
        return ""


# ── Duplicate ROM Finder ─────────────────────────────────────────────

def find_duplicate_roms(rom_dirs: Optional[list[str]] = None,
                        min_size: int = 1024,
                        extensions: Optional[set] = None) -> dict:
    """Find duplicate ROM files across multiple directories by hash.

    Returns dict with:
      - duplicates: list of duplicate groups
      - total_wasted: bytes that could be freed
      - file_count: total files scanned
    """
    if rom_dirs is None:
        hs_root = Path(get("paths.hyperspin_root", r"D:\Arcade"))
        rom_dirs = [str(hs_root)]

    if extensions is None:
        extensions = {
            ".zip", ".7z", ".rar",  # Archives
            ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba",  # Nintendo
            ".md", ".smd", ".gen", ".gg", ".sms",  # Sega
            ".bin", ".iso", ".cue", ".chd", ".img",  # Disc
            ".rom", ".a26", ".a78", ".lnx",  # Atari
            ".pce", ".ngp", ".ngc", ".ws", ".wsc",  # Other
            ".n64", ".z64", ".v64", ".nds", ".3ds",  # Modern Nintendo
            ".pbp", ".cso", ".xci", ".nsp",  # Sony/Switch
        }

    log.info("Scanning for duplicate ROMs across %d directories...", len(rom_dirs))

    # Phase 1: Group by size (fast pre-filter)
    size_groups: dict[int, list[Path]] = defaultdict(list)
    file_count = 0
    skipped = 0

    for rom_dir in rom_dirs:
        root = Path(rom_dir)
        if not root.exists():
            continue
        for filepath in root.rglob("*"):
            if not filepath.is_file():
                continue
            if extensions and filepath.suffix.lower() not in extensions:
                continue
            try:
                size = filepath.stat().st_size
                if size < min_size:
                    skipped += 1
                    continue
                size_groups[size].append(filepath)
                file_count += 1
            except (OSError, PermissionError):
                skipped += 1

    log.info("Scanned %d files, %d skipped. %d size groups with potential dupes.",
             file_count, skipped,
             sum(1 for g in size_groups.values() if len(g) > 1))

    # Phase 2: Hash files that share the same size
    hash_groups: dict[str, list[Path]] = defaultdict(list)
    hashed = 0

    for size, files in size_groups.items():
        if len(files) < 2:
            continue
        for filepath in files:
            file_hash = _hash_file(filepath)
            if file_hash:
                hash_groups[file_hash].append(filepath)
                hashed += 1

    log.info("Hashed %d candidate files.", hashed)

    # Phase 3: Build duplicate report
    duplicates = []
    total_wasted = 0

    for file_hash, files in hash_groups.items():
        if len(files) < 2:
            continue
        file_size = files[0].stat().st_size
        wasted = file_size * (len(files) - 1)
        total_wasted += wasted

        duplicates.append({
            "hash": file_hash,
            "size": file_size,
            "size_human": _human_size(file_size),
            "count": len(files),
            "wasted": wasted,
            "wasted_human": _human_size(wasted),
            "files": [str(f) for f in sorted(files)],
        })

    # Sort by wasted space descending
    duplicates.sort(key=lambda d: d["wasted"], reverse=True)

    log.info("Found %d duplicate groups. Total recoverable: %s",
             len(duplicates), _human_size(total_wasted))
    audit("duplicate_scan", f"{len(duplicates)} groups, {_human_size(total_wasted)} recoverable")

    return {
        "duplicates": duplicates,
        "total_wasted": total_wasted,
        "total_wasted_human": _human_size(total_wasted),
        "file_count": file_count,
        "duplicate_groups": len(duplicates),
    }


# ── Redundant Emulator Version Finder ────────────────────────────────

def find_redundant_emulators() -> dict:
    """Identify emulators with multiple installed versions."""
    emu_root = Path(get("paths.emulators_root", r"D:\Arcade\emulators"))
    if not emu_root.exists():
        return {"groups": [], "total_dirs": 0}

    dirs = sorted([d.name for d in emu_root.iterdir() if d.is_dir()])

    # Detect version groups by normalizing names
    import re
    groups: dict[str, list[dict]] = defaultdict(list)

    for dirname in dirs:
        # Normalize: strip version numbers, punctuation, extra words
        normalized = dirname.lower()
        normalized = re.sub(r'[\s\-_]+', ' ', normalized)
        normalized = re.sub(r'\b(v?\d+[\d.]*\w*)\b', '', normalized)
        normalized = re.sub(r'\b(latest|version|emulator|alternative|custom|vulkan|canary|early access)\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        if not normalized:
            normalized = dirname.lower()

        # Calculate directory size
        dir_path = emu_root / dirname
        try:
            total_size = sum(f.stat().st_size for f in dir_path.rglob("*") if f.is_file())
        except (OSError, PermissionError):
            total_size = 0

        groups[normalized].append({
            "name": dirname,
            "path": str(dir_path),
            "size": total_size,
            "size_human": _human_size(total_size),
        })

    # Filter to groups with multiple versions
    redundant = []
    for base_name, versions in groups.items():
        if len(versions) < 2:
            continue
        group_size = sum(v["size"] for v in versions)
        # Keep the largest (likely most complete), flag the rest
        versions.sort(key=lambda v: v["size"], reverse=True)
        redundant.append({
            "base_name": base_name,
            "count": len(versions),
            "total_size": group_size,
            "total_size_human": _human_size(group_size),
            "potential_savings": sum(v["size"] for v in versions[1:]),
            "potential_savings_human": _human_size(sum(v["size"] for v in versions[1:])),
            "versions": versions,
            "recommended_keep": versions[0]["name"],
        })

    redundant.sort(key=lambda g: g["potential_savings"], reverse=True)

    total_savings = sum(g["potential_savings"] for g in redundant)
    log.info("Found %d emulator groups with redundant versions. Potential savings: %s",
             len(redundant), _human_size(total_savings))

    return {
        "groups": redundant,
        "total_dirs": len(dirs),
        "redundant_groups": len(redundant),
        "potential_savings": total_savings,
        "potential_savings_human": _human_size(total_savings),
    }


# ── Large File Finder ────────────────────────────────────────────────

def find_large_files(root_dir: Optional[str] = None,
                     min_size_mb: int = 500,
                     limit: int = 50) -> list[dict]:
    """Find the largest files under a directory."""
    if root_dir is None:
        root_dir = get("paths.hyperspin_root", r"D:\Arcade")

    root = Path(root_dir)
    min_bytes = min_size_mb * 1048576
    large_files = []

    log.info("Scanning for files > %d MB under %s...", min_size_mb, root)

    for filepath in root.rglob("*"):
        if not filepath.is_file():
            continue
        try:
            size = filepath.stat().st_size
            if size >= min_bytes:
                large_files.append({
                    "path": str(filepath),
                    "size": size,
                    "size_human": _human_size(size),
                    "extension": filepath.suffix.lower(),
                    "modified": filepath.stat().st_mtime,
                })
        except (OSError, PermissionError):
            continue

    large_files.sort(key=lambda f: f["size"], reverse=True)
    result = large_files[:limit]

    total = sum(f["size"] for f in result)
    log.info("Found %d files > %d MB (showing top %d, total: %s)",
             len(large_files), min_size_mb, len(result), _human_size(total))

    return result


# ── Empty Directory Finder ───────────────────────────────────────────

def find_empty_dirs(root_dir: Optional[str] = None) -> list[str]:
    """Find empty directories that can be safely removed."""
    if root_dir is None:
        root_dir = get("paths.hyperspin_root", r"D:\Arcade")

    root = Path(root_dir)
    empty = []

    for dirpath in root.rglob("*"):
        if not dirpath.is_dir():
            continue
        try:
            if not any(dirpath.iterdir()):
                empty.append(str(dirpath))
        except (OSError, PermissionError):
            continue

    log.info("Found %d empty directories", len(empty))
    return sorted(empty)


# ── Disk Usage Summary ───────────────────────────────────────────────

def disk_usage_summary() -> dict:
    """Get disk usage breakdown by top-level directory."""
    hs_root = Path(get("paths.hyperspin_root", r"D:\Arcade"))
    if not hs_root.exists():
        return {}

    import shutil
    usage = shutil.disk_usage(str(hs_root))

    # Top-level directory sizes (quick scan — files only at depth 0-1)
    dir_sizes = {}
    for d in sorted(hs_root.iterdir()):
        if not d.is_dir():
            continue
        try:
            total = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            dir_sizes[d.name] = {
                "size": total,
                "size_human": _human_size(total),
            }
        except (OSError, PermissionError):
            dir_sizes[d.name] = {"size": 0, "size_human": "N/A"}

    # Sort by size
    sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1]["size"], reverse=True)

    return {
        "drive_total": usage.total,
        "drive_used": usage.used,
        "drive_free": usage.free,
        "drive_total_human": _human_size(usage.total),
        "drive_used_human": _human_size(usage.used),
        "drive_free_human": _human_size(usage.free),
        "drive_used_pct": round(usage.used / usage.total * 100, 1),
        "top_dirs": sorted_dirs[:30],
    }


# ── Full Space Optimization Report ──────────────────────────────────

def full_optimization_report() -> dict:
    """Generate a comprehensive space optimization report."""
    log.info("Generating full space optimization report...")

    report = {
        "disk": disk_usage_summary(),
        "redundant_emulators": find_redundant_emulators(),
        "empty_dirs": find_empty_dirs(),
    }

    # Don't run full duplicate scan by default (too slow for 12TB)
    # Instead, provide instructions
    report["recommendations"] = [
        {
            "action": "Consolidate redundant emulators",
            "details": f"{report['redundant_emulators']['redundant_groups']} emulator groups have multiple versions",
            "savings": report["redundant_emulators"]["potential_savings_human"],
            "risk": "LOW — keep latest, archive old to backup drive",
        },
        {
            "action": "Clean empty directories",
            "details": f"{len(report['empty_dirs'])} empty directories found",
            "savings": "Minimal (metadata only)",
            "risk": "LOW — no data lost",
        },
        {
            "action": "Run targeted duplicate scan on largest systems",
            "details": "Use: python main.py optimize duplicates --dir <path>",
            "savings": "Varies — typically 5-20% of ROM collections",
            "risk": "MEDIUM — verify before deleting",
        },
        {
            "action": "Compress old MAME ROM backup",
            "details": "MAME - 0.211 and previous directory (CORRUPTED — needs chkdsk first)",
            "savings": "Could be significant",
            "risk": "HIGH — run chkdsk D: /f first to repair corruption",
        },
        {
            "action": "Upgrade MAME 0.228 → latest",
            "details": "Current MAME is 50+ versions behind. New version may have better ROM compression.",
            "savings": "Varies",
            "risk": "LOW with toolkit snapshot/rollback",
        },
    ]

    audit("space_report", json.dumps({
        "free_gb": round(report["disk"].get("drive_free", 0) / 1073741824, 1),
        "redundant_groups": report["redundant_emulators"]["redundant_groups"],
        "empty_dirs": len(report["empty_dirs"]),
    }))

    return report
