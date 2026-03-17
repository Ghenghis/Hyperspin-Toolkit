"""Drive Indexer & Identification Engine.

Provides:
  - Drive identification by serial number (letter-independent)
  - Collection type auto-detection
  - Drive manifest generation (file counts, sizes, folder trees)
  - Registry loading/saving from drive_registry.json
  - Cross-drive inventory queries
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("drive_indexer")

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "drive_registry.json"

# ---------------------------------------------------------------------------
# Collection type detection signatures
# ---------------------------------------------------------------------------
COLLECTION_SIGNATURES = {
    "HyperSpin + RocketLauncher": {
        "required": ["Arcade"],
        "indicators": [
            "BACKUP FILES - HYPERSPIN & ROCKETLAUNCHER",
            "HyperSpin_Backups",
            "HyperSpin_Recovery",
            "SETUP USER GUIDE - FOR HYPERSPIN",
        ],
        "min_arcade_systems": 50,
    },
    "HyperSpin Attract Mode": {
        "required": ["Arcade"],
        "sub_indicators": {
            "Arcade": ["collections", "emulators", "layouts", "plugins"],
        },
    },
    "CORE - TYPE R": {
        "required": ["CORE - TYPE R"],
        "sub_indicators": {
            "CORE - TYPE R": ["collections", "core", "launchers.windows", "layouts", "meta"],
        },
    },
    "Batocera": {
        "required": ["roms", "bios"],
        "indicators": ["themes", "decorations", "saves", "screenshots"],
    },
    "ROM Backup / PC Games": {
        "required": ["Games"],
        "indicators": [],
    },
}


# ---------------------------------------------------------------------------
# Registry management
# ---------------------------------------------------------------------------

def load_registry(path: Path | str | None = None) -> dict:
    """Load the drive registry JSON."""
    p = Path(path) if path else REGISTRY_PATH
    if not p.exists():
        log.warning("Drive registry not found: %s", p)
        return {"drives": [], "system_drives": [], "collection_types": {}}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_registry(data: dict, path: Path | str | None = None) -> None:
    """Save the drive registry JSON."""
    p = Path(path) if path else REGISTRY_PATH
    data["_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    log.info("Registry saved to %s", p)


def find_drive_by_serial(serial: str, registry: dict | None = None) -> dict | None:
    """Look up a drive entry by its serial number."""
    reg = registry or load_registry()
    for d in reg.get("drives", []):
        if d.get("serial") == serial:
            return d
    for d in reg.get("system_drives", []):
        if d.get("serial") == serial:
            return d
    return None


def find_drive_by_tag(tag: str, registry: dict | None = None) -> dict | None:
    """Look up a drive entry by its tag name."""
    reg = registry or load_registry()
    for d in reg.get("drives", []) + reg.get("system_drives", []):
        if d.get("tag") == tag:
            return d
    return None


def find_drive_by_letter(letter: str, registry: dict | None = None) -> dict | None:
    """Look up a drive entry by its current letter."""
    letter = letter.rstrip(":").upper()
    reg = registry or load_registry()
    for d in reg.get("drives", []) + reg.get("system_drives", []):
        if d.get("current_letter", "").upper() == letter:
            return d
    return None


# ---------------------------------------------------------------------------
# Live drive enumeration (Windows PowerShell)
# ---------------------------------------------------------------------------

def enumerate_physical_disks() -> list[dict]:
    """Query Windows for all physical disks with serial, model, health."""
    try:
        cmd = (
            'Get-PhysicalDisk | Select-Object DeviceId, FriendlyName, SerialNumber, '
            'HealthStatus, @{N="SizeGB";E={[math]::Round($_.Size/1GB,2)}} '
            '| ConvertTo-Json -Compress'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning("Failed to enumerate disks: %s", result.stderr[:200])
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as exc:
        log.warning("enumerate_physical_disks error: %s", exc)
        return []


def enumerate_volumes() -> list[dict]:
    """Query Windows for all volumes with health, free space, labels."""
    try:
        cmd = (
            "Get-Volume | Where-Object { $_.DriveLetter } | "
            'Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus, '
            '@{N="SizeGB";E={[math]::Round($_.Size/1GB,2)}}, '
            '@{N="FreeGB";E={[math]::Round($_.SizeRemaining/1GB,2)}} '
            '| ConvertTo-Json -Compress'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return []
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        return data
    except Exception as exc:
        log.warning("enumerate_volumes error: %s", exc)
        return []


def get_disk_to_volume_map() -> dict[int, list[str]]:
    """Map disk numbers to drive letters."""
    try:
        cmd = (
            "Get-Partition | Where-Object { $_.DriveLetter } | "
            'Select-Object DiskNumber, DriveLetter | ConvertTo-Json -Compress'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]
        mapping: dict[int, list[str]] = {}
        for item in data:
            disk_num = item.get("DiskNumber")
            letter = item.get("DriveLetter")
            if disk_num is not None and letter:
                mapping.setdefault(disk_num, []).append(str(letter))
        return mapping
    except Exception as exc:
        log.warning("get_disk_to_volume_map error: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Collection type detection
# ---------------------------------------------------------------------------

def detect_collection_type(drive_root: str) -> str:
    """Auto-detect the collection type on a drive by examining top-level dirs."""
    root = Path(drive_root)
    if not root.exists():
        return "Unknown"

    top_dirs = {d.name for d in root.iterdir() if d.is_dir()}

    # Check CORE - TYPE R first (specific)
    sig = COLLECTION_SIGNATURES["CORE - TYPE R"]
    if all(r in top_dirs for r in sig["required"]):
        sub_path = root / "CORE - TYPE R"
        if sub_path.exists():
            sub_dirs = {d.name for d in sub_path.iterdir() if d.is_dir()}
            expected = set(sig["sub_indicators"]["CORE - TYPE R"])
            if len(expected & sub_dirs) >= 3:
                return "CORE - TYPE R"

    # Check Batocera
    sig = COLLECTION_SIGNATURES["Batocera"]
    if all(r in top_dirs for r in sig["required"]):
        return "Batocera"

    # Check HyperSpin variants
    if "Arcade" in top_dirs:
        arcade_path = root / "Arcade"
        arcade_subs = {d.name for d in arcade_path.iterdir() if d.is_dir()} if arcade_path.exists() else set()

        # Check Attract Mode (has collections/emulators/layouts under Arcade)
        attract_sig = COLLECTION_SIGNATURES["HyperSpin Attract Mode"]
        expected_subs = set(attract_sig["sub_indicators"]["Arcade"])
        if len(expected_subs & arcade_subs) >= 3:
            return "HyperSpin Attract Mode"

        # Check standard HyperSpin + RL
        hs_sig = COLLECTION_SIGNATURES["HyperSpin + RocketLauncher"]
        indicators = set(hs_sig["indicators"])
        if len(indicators & top_dirs) >= 2:
            return "HyperSpin + RocketLauncher"

        # Has Arcade but unclear type
        if len(arcade_subs) > 20:
            return "HyperSpin + RocketLauncher"

    # Check ROM Backup
    sig = COLLECTION_SIGNATURES["ROM Backup / PC Games"]
    if "Games" in top_dirs:
        return "ROM Backup / PC Games"

    return "Unknown"


# ---------------------------------------------------------------------------
# Drive manifest generation
# ---------------------------------------------------------------------------

def generate_drive_manifest(drive_letter: str, max_depth: int = 2) -> dict:
    """Generate a manifest of a drive's contents.

    Returns:
        Dict with file counts, total size, top-level tree, collection type.
    """
    root = Path(f"{drive_letter.rstrip(':')}:/")
    if not root.exists():
        return {"error": f"Drive {drive_letter}: not accessible"}

    manifest = {
        "drive_letter": drive_letter.rstrip(":").upper(),
        "label": "",
        "collection_type": "Unknown",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top_level_dirs": [],
        "top_level_files": [],
        "total_top_dirs": 0,
        "total_top_files": 0,
    }

    # Get volume label
    try:
        volumes = enumerate_volumes()
        for v in volumes:
            if str(v.get("DriveLetter", "")).upper() == manifest["drive_letter"]:
                manifest["label"] = v.get("FileSystemLabel", "")
                manifest["size_gb"] = v.get("SizeGB", 0)
                manifest["free_gb"] = v.get("FreeGB", 0)
                manifest["health"] = v.get("HealthStatus", "Unknown")
                break
    except Exception:
        pass

    # Scan top-level
    try:
        for item in root.iterdir():
            if item.is_dir():
                manifest["top_level_dirs"].append(item.name)
            else:
                manifest["top_level_files"].append(item.name)
    except PermissionError:
        manifest["error"] = "Permission denied reading root"

    manifest["total_top_dirs"] = len(manifest["top_level_dirs"])
    manifest["total_top_files"] = len(manifest["top_level_files"])

    # Detect collection type
    manifest["collection_type"] = detect_collection_type(str(root))

    return manifest


# ---------------------------------------------------------------------------
# Inventory & summary
# ---------------------------------------------------------------------------

def full_inventory() -> dict:
    """Build a complete live inventory of all connected drives.

    Merges live disk data with registry information.
    """
    registry = load_registry()
    disks = enumerate_physical_disks()
    volumes = enumerate_volumes()
    disk_vol_map = get_disk_to_volume_map()

    inventory = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_physical_disks": len(disks),
        "total_volumes": len(volumes),
        "gaming_drives": [],
        "system_drives": [],
        "warning_drives": [],
        "unregistered_drives": [],
    }

    registered_letters = set()
    for entry in registry.get("drives", []) + registry.get("system_drives", []):
        registered_letters.add(entry.get("current_letter", "").upper())

    for vol in volumes:
        letter = str(vol.get("DriveLetter", "")).upper()
        health = vol.get("HealthStatus", "")
        reg_entry = find_drive_by_letter(letter, registry)

        vol_info = {
            "letter": letter,
            "label": vol.get("FileSystemLabel", ""),
            "size_gb": vol.get("SizeGB", 0),
            "free_gb": vol.get("FreeGB", 0),
            "health": health,
            "registered": reg_entry is not None,
            "tag": reg_entry.get("tag") if reg_entry else None,
            "role": reg_entry.get("role") if reg_entry else None,
        }

        if health == "Warning":
            inventory["warning_drives"].append(vol_info)

        if reg_entry:
            if reg_entry.get("tag", "").startswith("OS_") or reg_entry.get("tag") == "STORAGE_SSD":
                inventory["system_drives"].append(vol_info)
            else:
                inventory["gaming_drives"].append(vol_info)
        elif letter not in registered_letters:
            inventory["unregistered_drives"].append(vol_info)

    return inventory


def drive_summary() -> dict:
    """Quick summary for CLI/dashboard."""
    inv = full_inventory()
    return {
        "total_disks": inv["total_physical_disks"],
        "total_volumes": inv["total_volumes"],
        "gaming_drives": len(inv["gaming_drives"]),
        "system_drives": len(inv["system_drives"]),
        "warning_count": len(inv["warning_drives"]),
        "warning_drives": [
            f"{d['letter']}: {d['label']} ({d['health']})"
            for d in inv["warning_drives"]
        ],
        "unregistered": len(inv["unregistered_drives"]),
    }
