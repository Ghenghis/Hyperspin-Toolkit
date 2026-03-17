"""Smart Drive Index — Fingerprint-based drive identification system.

Drives are identified by a unique fingerprint (volume serial + content hash),
NOT by drive letter.  When Windows reassigns a letter the index detects
"same drive, new letter" and auto-heals every path reference.

Features:
  - Volume serial based identity that survives letter reassignment
  - Content-structure hashing as secondary identity
  - Drive-type detection (NVMe / SSD / HDD) for performance guidance
  - Automatic new-drive discovery and indexing
  - Missing-drive tracking (remembers drives that are disconnected)
  - Role assignment by fingerprint, not letter
  - One-call ``reconcile()`` that heals everything on startup
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import string
import subprocess
from pathlib import Path
from typing import Any, Optional

# ── Paths ─────────────────────────────────────────────────────────────
TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE   = TOOLKIT_ROOT / "drives.json"

# ── Arcade content fingerprints ──────────────────────────────────────
ARCADE_FINGERPRINTS = [
    "HyperSpin", "RocketLauncher", "emulators", "Arcade",
    "Arcade\\HyperSpin", "Arcade\\emulators", "Arcade\\RocketLauncher",
    "Arcade\\ROMs", "Arcade\\Media", "ROMs", "MAME",
]
ARCADE_ROOT_NAMES = ["Arcade", "Games", "ROMs", "Emulators", "HyperSpin"]
MIN_GAME_DRIVE_GB = 200


# =====================================================================
# Drive identity helpers
# =====================================================================

def _get_volume_serial(letter: str) -> str | None:
    """Return the volume serial number string for a Windows drive letter."""
    if platform.system() != "Windows":
        return None
    try:
        result = subprocess.run(
            ["vol", f"{letter}:"],
            capture_output=True, text=True, timeout=5, shell=True,
        )
        for line in result.stdout.splitlines():
            # e.g.  "Volume Serial Number is 1234-ABCD"
            if "Serial Number" in line:
                return line.split("is")[-1].strip()
    except Exception:
        pass
    return None


def _get_volume_label(letter: str) -> str:
    """Return the volume label for a Windows drive."""
    try:
        result = subprocess.run(
            ["vol", f"{letter}:"],
            capture_output=True, text=True, timeout=3, shell=True,
        )
        for line in result.stdout.splitlines():
            if "Volume" in line and " is " in line and "Serial" not in line:
                return line.split(" is ")[-1].strip()
    except Exception:
        pass
    return ""


def _content_hash(letter: str) -> str:
    """Build a lightweight hash of the top-level directory structure.

    This is NOT a full content hash (too slow).  It hashes the sorted names
    of immediate subdirectories on the drive root so we can recognise the
    same content even after a letter change.
    """
    root = Path(f"{letter}:\\")
    try:
        names = sorted(
            e.name for e in root.iterdir()
            if e.is_dir() and not e.name.startswith("$") and e.name != "System Volume Information"
        )
    except Exception:
        names = []
    return hashlib.sha1("|".join(names).encode()).hexdigest()[:16]


def _detect_drive_type(letter: str) -> str:
    """Detect physical media type: NVMe, SSD, or HDD.

    Uses ``Get-PhysicalDisk`` via PowerShell on Windows.
    Falls back to 'Unknown' if detection fails.
    """
    if platform.system() != "Windows":
        return "Unknown"
    try:
        ps = (
            f"Get-Partition -DriveLetter '{letter}' | "
            f"Get-Disk | Get-PhysicalDisk | "
            f"Select-Object -ExpandProperty MediaType"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        media = result.stdout.strip()
        if not media or media == "Unspecified":
            # Try bus type for NVMe detection
            ps2 = (
                f"Get-Partition -DriveLetter '{letter}' | "
                f"Get-Disk | Get-PhysicalDisk | "
                f"Select-Object -ExpandProperty BusType"
            )
            r2 = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps2],
                capture_output=True, text=True, timeout=10,
            )
            bus = r2.stdout.strip()
            if bus == "NVMe":
                return "NVMe"
            elif bus in ("SATA", "ATA"):
                # SSD vs HDD: check MediaType again or use SpindleSpeed
                if media == "SSD":
                    return "SSD"
                return "HDD"
            return bus or "Unknown"
        if media == "SSD":
            # Check if it's actually NVMe
            ps3 = (
                f"Get-Partition -DriveLetter '{letter}' | "
                f"Get-Disk | Get-PhysicalDisk | "
                f"Select-Object -ExpandProperty BusType"
            )
            r3 = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps3],
                capture_output=True, text=True, timeout=10,
            )
            if r3.stdout.strip() == "NVMe":
                return "NVMe"
            return "SSD"
        return media  # "HDD", "SSD", etc.
    except Exception:
        return "Unknown"


def _drive_usage(letter: str) -> dict[str, Any]:
    """Return disk usage info for a drive letter."""
    try:
        usage = shutil.disk_usage(f"{letter}:\\")
        total_gb = usage.total / (1024 ** 3)
        used_gb  = usage.used  / (1024 ** 3)
        free_gb  = usage.free  / (1024 ** 3)
        return {
            "total_gb": round(total_gb, 1),
            "used_gb":  round(used_gb, 1),
            "free_gb":  round(free_gb, 1),
            "total_human": _human_gb(usage.total),
            "used_human":  _human_gb(usage.used),
            "free_human":  _human_gb(usage.free),
            "used_pct": round(used_gb / total_gb * 100, 1) if total_gb > 0 else 0,
        }
    except Exception:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0,
                "total_human": "?", "used_human": "?", "free_human": "?", "used_pct": 0}


def _human_gb(n_bytes: int) -> str:
    tb = n_bytes / (1024 ** 4)
    if tb >= 1:
        return f"{tb:.1f} TB"
    return f"{n_bytes / (1024 ** 3):.1f} GB"


def _detect_arcade_content(letter: str) -> dict[str, Any]:
    """Scan a drive for arcade content fingerprints."""
    drive_root = Path(f"{letter}:\\")
    found_types: list[str] = []
    arcade_root: str | None = None
    confidence = 0

    for fp in ARCADE_FINGERPRINTS:
        if (drive_root / fp).exists():
            found_types.append(fp)
            confidence += 10
            top = fp.split("\\")[0]
            if top in ARCADE_ROOT_NAMES and arcade_root is None:
                arcade_root = top

    if arcade_root is None:
        for name in ARCADE_ROOT_NAMES:
            candidate = drive_root / name
            if candidate.is_dir():
                for sub in ("HyperSpin", "emulators", "ROMs", "RocketLauncher"):
                    if (candidate / sub).is_dir():
                        arcade_root = name
                        found_types.append(f"{name}\\{sub}")
                        confidence += 15
                        break
                if arcade_root:
                    break

    return {
        "found": len(found_types) > 0,
        "arcade_root": arcade_root or "Arcade",
        "content_types": found_types,
        "confidence": min(confidence, 100),
    }


def _make_fingerprint(serial: str | None, content_hash: str) -> str:
    """Combine volume serial + content hash into a stable fingerprint ID."""
    raw = f"{serial or 'no-serial'}:{content_hash}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# =====================================================================
# Index data model
# =====================================================================

def _empty_index() -> dict[str, Any]:
    return {
        "version": 2,
        "drives": {},          # fingerprint → drive record
        "roles": {             # role → fingerprint
            "primary":   None,
            "secondary": None,
            "tertiary":  None,
        },
        "last_scan": None,
        # Legacy compat keys (resolved by load_state / config.py)
        "primary": None,
        "secondary": None,
        "tertiary": None,
        "arcade_root": "Arcade",
        "secondary_root": "Arcade",
        "tertiary_root": "Arcade",
    }


def load_index() -> dict[str, Any]:
    """Load the drive index from drives.json, migrating v1 format if needed."""
    if not INDEX_FILE.exists():
        return _empty_index()
    try:
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return _empty_index()

    # Migrate v1 (flat letter-based) → v2 (fingerprint-based)
    if data.get("version", 1) < 2:
        return _migrate_v1(data)
    return data


def _migrate_v1(old: dict) -> dict[str, Any]:
    """Migrate legacy drives.json (letter-based) to v2 fingerprint index."""
    idx = _empty_index()
    for role in ("primary", "secondary", "tertiary"):
        letter = old.get(role)
        if letter and os.path.exists(f"{letter}:\\"):
            serial = _get_volume_serial(letter)
            chash  = _content_hash(letter)
            fp     = _make_fingerprint(serial, chash)
            root_key = {"primary": "arcade_root", "secondary": "secondary_root",
                        "tertiary": "tertiary_root"}.get(role, "arcade_root")
            arcade_root = old.get(root_key, "Arcade")
            arcade_info = _detect_arcade_content(letter)
            idx["drives"][fp] = {
                "fingerprint":   fp,
                "volume_serial": serial,
                "content_hash":  chash,
                "label":         _get_volume_label(letter),
                "current_letter": letter,
                "last_letter":   letter,
                "arcade_root":   arcade_root,
                "content_types": arcade_info["content_types"],
                "confidence":    arcade_info["confidence"],
                "drive_type":    "Unknown",  # detect later
                "role":          role,
                "connected":     True,
                "first_seen":    datetime.datetime.now().isoformat(),
                "last_seen":     datetime.datetime.now().isoformat(),
            }
            idx["roles"][role] = fp
    _sync_legacy_keys(idx)
    save_index(idx)
    return idx


def save_index(idx: dict[str, Any]) -> None:
    """Persist the drive index to drives.json."""
    _sync_legacy_keys(idx)
    INDEX_FILE.write_text(json.dumps(idx, indent=2), encoding="utf-8")


def _sync_legacy_keys(idx: dict[str, Any]) -> None:
    """Keep legacy flat keys in sync so config.py can read them."""
    roles  = idx.get("roles") or {}
    drives = idx.get("drives") or {}
    for role in ("primary", "secondary", "tertiary"):
        fp = roles.get(role)
        if fp and fp in drives:
            # Fingerprint-resolved assignment — update flat key from live drive record
            drv = drives[fp]
            idx[role] = drv["current_letter"]
            root_key = {"primary": "arcade_root", "secondary": "secondary_root",
                        "tertiary": "tertiary_root"}[role]
            idx[root_key] = drv["arcade_root"]
        elif fp:
            # Fingerprint set but drive record missing (drive was purged) — clear flat key
            idx[role] = None
        # fp is None → role not yet assigned; preserve any existing flat key value


# =====================================================================
# Backward-compat wrappers (used by existing code)
# =====================================================================

def load_state() -> dict:
    """Backward-compatible: return flat dict that config.py / old code expects."""
    idx = load_index()
    _sync_legacy_keys(idx)
    return idx


def save_state(state: dict) -> None:
    """Backward-compatible save."""
    if "roles" not in state:
        # v1-style flat dict — normalize to v2 so round-trip via load_state works cleanly
        state = {
            **state,
            "version": 2,
            "roles":  {},
            "drives": state.get("drives", {}),
        }
    save_index(state)


# =====================================================================
# Core scanning
# =====================================================================

def _get_all_drives() -> list[str]:
    """Return all available drive letters (Windows only)."""
    if platform.system() != "Windows":
        return []
    return [l for l in string.ascii_uppercase if os.path.exists(f"{l}:\\")]


def scan_drives(min_gb: float = MIN_GAME_DRIVE_GB) -> list[dict[str, Any]]:
    """Scan all connected drives and return info about each one.

    Returns list of drive dicts sorted by arcade confidence then size.
    """
    system_drive = os.environ.get("SystemDrive", "C:")[0].upper()
    results: list[dict[str, Any]] = []

    for letter in _get_all_drives():
        usage = _drive_usage(letter)
        label = _get_volume_label(letter)
        is_system = letter.upper() == system_drive

        arcade_info = (
            _detect_arcade_content(letter)
            if not is_system
            else {"found": False, "arcade_root": "Arcade", "content_types": [], "confidence": 0}
        )

        serial = _get_volume_serial(letter)
        chash  = _content_hash(letter)
        fp     = _make_fingerprint(serial, chash)

        results.append({
            "letter":       letter,
            "label":        label,
            "fingerprint":  fp,
            "volume_serial": serial,
            "content_hash": chash,
            "is_system":    is_system,
            "is_arcade":    arcade_info["found"],
            "arcade_root":  arcade_info["arcade_root"],
            "content_types": arcade_info["content_types"],
            "confidence":   arcade_info["confidence"],
            **usage,
        })

    results.sort(key=lambda d: (not d["is_arcade"], -d.get("confidence", 0), -d["total_gb"]))
    return results


# =====================================================================
# Smart reconciliation — the heart of the system
# =====================================================================

def reconcile(idx: dict[str, Any] | None = None, *, detect_type: bool = False) -> dict[str, Any]:
    """Re-scan all drives and reconcile the index.

    This is the main entry point called on toolkit startup.  It:
      1. Scans every connected drive
      2. Matches each to a known fingerprint (by serial first, content hash second)
      3. Detects letter changes and updates the index
      4. Discovers brand-new drives and adds them
      5. Marks disconnected drives as offline
      6. Auto-assigns unassigned roles if arcade content is found
      7. Optionally detects drive type (NVMe/SSD/HDD) — slower

    Returns the updated index (also saved to disk).
    """
    if idx is None:
        idx = load_index()

    now = datetime.datetime.now().isoformat()
    scanned = scan_drives(min_gb=0)  # scan ALL drives, filter later

    # Build lookup maps for existing index entries
    by_serial: dict[str, str] = {}   # serial → fingerprint
    by_chash:  dict[str, str] = {}   # content_hash → fingerprint
    for fp, drv in idx["drives"].items():
        if drv.get("volume_serial"):
            by_serial[drv["volume_serial"]] = fp
        if drv.get("content_hash"):
            by_chash[drv["content_hash"]] = fp

    # Mark all indexed drives as disconnected; we'll flip connected ones back
    for drv in idx["drives"].values():
        drv["connected"] = False

    seen_fps: set[str] = set()
    events: list[dict[str, str]] = []

    for live in scanned:
        serial = live.get("volume_serial")
        chash  = live.get("content_hash", "")
        letter = live["letter"]
        matched_fp: str | None = None

        # Match strategy 1: volume serial (strongest identity)
        if serial and serial in by_serial:
            matched_fp = by_serial[serial]

        # Match strategy 2: content hash (handles re-formatted / new serial scenarios)
        if matched_fp is None and chash and chash in by_chash:
            candidate_fp = by_chash[chash]
            candidate = idx["drives"][candidate_fp]
            # Only match by content if the serial is absent or matches
            if not candidate.get("volume_serial") or candidate["volume_serial"] == serial:
                matched_fp = candidate_fp

        if matched_fp and matched_fp in idx["drives"]:
            # Known drive — update it
            drv = idx["drives"][matched_fp]
            old_letter = drv.get("current_letter")
            drv["connected"]      = True
            drv["current_letter"]  = letter
            drv["volume_serial"]   = serial or drv.get("volume_serial")
            drv["content_hash"]    = chash
            drv["label"]           = live["label"]
            drv["last_seen"]       = now
            drv["content_types"]   = live["content_types"]
            drv["confidence"]      = live["confidence"]

            if old_letter and old_letter != letter:
                drv["last_letter"] = old_letter
                events.append({
                    "type": "letter_changed",
                    "fingerprint": matched_fp,
                    "old_letter": old_letter,
                    "new_letter": letter,
                    "label": live["label"],
                })

            if detect_type and drv.get("drive_type", "Unknown") == "Unknown":
                drv["drive_type"] = _detect_drive_type(letter)

            seen_fps.add(matched_fp)
        else:
            # Brand new drive — index it
            new_fp = _make_fingerprint(serial, chash)
            if new_fp in idx["drives"]:
                # Fingerprint collision (extremely rare) — append letter
                new_fp = f"{new_fp}_{letter.lower()}"

            arcade_info = _detect_arcade_content(letter)
            drv_type = _detect_drive_type(letter) if detect_type else "Unknown"

            idx["drives"][new_fp] = {
                "fingerprint":    new_fp,
                "volume_serial":  serial,
                "content_hash":   chash,
                "label":          live["label"],
                "current_letter": letter,
                "last_letter":    letter,
                "arcade_root":    arcade_info["arcade_root"],
                "content_types":  arcade_info["content_types"],
                "confidence":     arcade_info["confidence"],
                "drive_type":     drv_type,
                "role":           None,
                "connected":      True,
                "is_system":      live.get("is_system", False),
                "first_seen":     now,
                "last_seen":      now,
                **{k: live[k] for k in ("total_gb", "used_gb", "free_gb",
                                         "total_human", "used_human", "free_human", "used_pct")
                   if k in live},
            }
            if arcade_info["found"] and not live.get("is_system", False):
                events.append({
                    "type": "new_arcade_drive",
                    "fingerprint": new_fp,
                    "letter": letter,
                    "label": live["label"],
                    "content": arcade_info["content_types"],
                })
            seen_fps.add(new_fp)

    # Flag disconnected drives
    for fp, drv in idx["drives"].items():
        if fp not in seen_fps and drv.get("connected"):
            drv["connected"] = False
            events.append({
                "type": "drive_disconnected",
                "fingerprint": fp,
                "last_letter": drv.get("current_letter"),
                "label": drv.get("label", ""),
            })

    # Validate existing role assignments — if the drive for a role changed
    # letter or went offline, handle it
    for role in ("primary", "secondary", "tertiary"):
        assigned_fp = idx["roles"].get(role)
        if assigned_fp and assigned_fp in idx["drives"]:
            drv = idx["drives"][assigned_fp]
            if not drv["connected"]:
                events.append({
                    "type": "role_drive_offline",
                    "role": role,
                    "fingerprint": assigned_fp,
                    "last_letter": drv.get("current_letter"),
                })

    # Auto-assign unassigned roles to unassigned arcade drives
    _auto_fill_roles(idx)

    idx["last_scan"] = now
    idx["events"] = events
    _sync_legacy_keys(idx)
    save_index(idx)
    return idx


def _auto_fill_roles(idx: dict[str, Any]) -> None:
    """Auto-assign unassigned roles to the best available arcade drives."""
    assigned_fps = set(fp for fp in idx["roles"].values() if fp)

    # Collect unassigned, connected arcade drives sorted by confidence → size
    candidates = [
        (fp, drv) for fp, drv in idx["drives"].items()
        if fp not in assigned_fps
        and drv.get("connected")
        and not drv.get("is_system")
        and drv.get("confidence", 0) > 0
    ]
    candidates.sort(key=lambda x: (-x[1].get("confidence", 0), -x[1].get("total_gb", 0)))

    for role in ("primary", "secondary", "tertiary"):
        if idx["roles"].get(role) is None and candidates:
            fp, drv = candidates.pop(0)
            idx["roles"][role] = fp
            drv["role"] = role


# =====================================================================
# Role management
# =====================================================================

def assign_role(role: str, letter: str, arcade_root: str = "Arcade",
                idx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Manually assign a drive letter to a role.  Indexes the drive if new."""
    if idx is None:
        idx = load_index()
    letter = letter.upper().strip(":\\")
    if role not in ("primary", "secondary", "tertiary"):
        raise ValueError(f"Unknown role: {role}")
    if not os.path.exists(f"{letter}:\\"):
        raise FileNotFoundError(f"Drive {letter}:\\ not found")

    # Find or create the drive record
    serial = _get_volume_serial(letter)
    chash  = _content_hash(letter)
    target_fp: str | None = None

    for fp, drv in idx["drives"].items():
        if drv.get("volume_serial") == serial and serial:
            target_fp = fp
            break
        if drv.get("content_hash") == chash:
            target_fp = fp
            break

    if target_fp is None:
        target_fp = _make_fingerprint(serial, chash)
        arcade_info = _detect_arcade_content(letter)
        now = datetime.datetime.now().isoformat()
        idx["drives"][target_fp] = {
            "fingerprint":    target_fp,
            "volume_serial":  serial,
            "content_hash":   chash,
            "label":          _get_volume_label(letter),
            "current_letter": letter,
            "last_letter":    letter,
            "arcade_root":    arcade_root,
            "content_types":  arcade_info["content_types"],
            "confidence":     arcade_info["confidence"],
            "drive_type":     "Unknown",
            "role":           role,
            "connected":      True,
            "is_system":      False,
            "first_seen":     now,
            "last_seen":      now,
        }
    else:
        idx["drives"][target_fp]["arcade_root"] = arcade_root
        idx["drives"][target_fp]["current_letter"] = letter
        idx["drives"][target_fp]["role"] = role

    # Unassign any drive currently holding this role
    old_fp = idx["roles"].get(role)
    if old_fp and old_fp in idx["drives"]:
        idx["drives"][old_fp]["role"] = None

    idx["roles"][role] = target_fp
    _sync_legacy_keys(idx)
    save_index(idx)
    return idx


def auto_assign(state: dict | None = None) -> dict:
    """Auto-detect drive roles via full reconciliation.

    Backward-compatible wrapper: returns the index with legacy keys synced.
    """
    idx = reconcile(detect_type=False)
    return idx


# =====================================================================
# Query helpers
# =====================================================================

def get_drive_for_role(role: str, idx: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Return the drive record for a given role, or None."""
    if idx is None:
        idx = load_index()
    fp = idx["roles"].get(role)
    if fp and fp in idx["drives"]:
        return idx["drives"][fp]
    return None


def resolve_path(template: str, state: dict | None = None) -> str:
    """Replace {primary}, {secondary}, {tertiary} tokens in a path string.

    Examples:
      resolve_path("{primary}:\\Arcade")
      resolve_path("{secondary}:\\ROMs")
      resolve_path("{primary_root}")
    """
    if state is None:
        state = load_index()

    primary   = state.get("primary")   or ""
    secondary = state.get("secondary") or primary
    tertiary  = state.get("tertiary")  or secondary
    arc_root  = state.get("arcade_root", "Arcade")
    sec_root  = state.get("secondary_root", "Arcade")
    ter_root  = state.get("tertiary_root", "Arcade")

    result = template
    result = result.replace("{primary}",        primary)
    result = result.replace("{secondary}",      secondary)
    result = result.replace("{tertiary}",       tertiary)
    result = result.replace("{primary_root}",   f"{primary}:\\{arc_root}" if primary else "")
    result = result.replace("{secondary_root}", f"{secondary}:\\{sec_root}" if secondary else "")
    result = result.replace("{tertiary_root}",  f"{tertiary}:\\{ter_root}" if tertiary else "")
    return result


def get_primary_root(state: dict | None = None) -> Path:
    """Return the primary arcade root Path."""
    if state is None:
        state = load_index()
    letter = state.get("primary") or ""
    root   = state.get("arcade_root", "Arcade")
    return Path(f"{letter}:\\{root}") if letter else Path(".")


def get_secondary_root(state: dict | None = None) -> Optional[Path]:
    """Return the secondary arcade root Path, or None if not assigned."""
    if state is None:
        state = load_index()
    letter = state.get("secondary")
    if not letter:
        return None
    root = state.get("secondary_root", "Arcade")
    return Path(f"{letter}:\\{root}")


def get_tertiary_root(state: dict | None = None) -> Optional[Path]:
    """Return the tertiary arcade root Path, or None if not assigned."""
    if state is None:
        state = load_index()
    letter = state.get("tertiary")
    if not letter:
        return None
    root = state.get("tertiary_root", "Arcade")
    return Path(f"{letter}:\\{root}")


def drive_status(state: dict | None = None) -> dict[str, Any]:
    """Return current drive assignment status with live disk usage."""
    idx = load_index() if state is None else state
    _sync_legacy_keys(idx)

    result: dict[str, Any] = {
        "drives": {},
        "last_scan": idx.get("last_scan"),
        "index_version": idx.get("version", 1),
        "total_indexed": len(idx.get("drives", {})),
    }

    for role in ("primary", "secondary", "tertiary"):
        fp = idx["roles"].get(role)
        if not fp or fp not in idx.get("drives", {}):
            result["drives"][role] = {"assigned": False}
            continue

        drv = idx["drives"][fp]
        letter = drv.get("current_letter", "")
        usage = _drive_usage(letter) if letter and os.path.exists(f"{letter}:\\") else {}
        root_path = Path(f"{letter}:\\{drv.get('arcade_root', 'Arcade')}") if letter else Path(".")

        result["drives"][role] = {
            "assigned":      True,
            "fingerprint":   fp,
            "letter":        letter,
            "path":          str(root_path),
            "label":         drv.get("label", ""),
            "drive_type":    drv.get("drive_type", "Unknown"),
            "connected":     drv.get("connected", False),
            "root_exists":   root_path.exists() if letter else False,
            "content":       drv.get("content_types", []),
            "confidence":    drv.get("confidence", 0),
            **usage,
        }

    return result


def list_indexed_drives(idx: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return all drives in the index (connected and disconnected)."""
    if idx is None:
        idx = load_index()
    drives = []
    for fp, drv in idx.get("drives", {}).items():
        drives.append({
            "fingerprint":  fp,
            "letter":       drv.get("current_letter", "?"),
            "label":        drv.get("label", ""),
            "role":         drv.get("role"),
            "connected":    drv.get("connected", False),
            "drive_type":   drv.get("drive_type", "Unknown"),
            "arcade_root":  drv.get("arcade_root", ""),
            "content_types": drv.get("content_types", []),
            "confidence":   drv.get("confidence", 0),
            "total_gb":     drv.get("total_gb", 0),
            "first_seen":   drv.get("first_seen", ""),
            "last_seen":    drv.get("last_seen", ""),
        })
    return drives


# =====================================================================
# MCP stdio entry point
# =====================================================================

def _mcp_main() -> None:
    """Minimal MCP stdio shim so Goose can call drive tools."""
    import sys
    import json as _json
    import traceback

    TOOLS = [
        {
            "name": "drives_scan",
            "description": "Scan all connected drives, index them by fingerprint, and identify arcade content.",
            "inputSchema": {"type": "object", "properties": {
                "min_gb": {"type": "number", "description": "Minimum size in GB (default: 200)", "default": 200}
            }},
        },
        {
            "name": "drives_status",
            "description": "Show current drive role assignments with fingerprints and live disk usage.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "drives_set",
            "description": "Assign a drive letter to a role. The drive is identified by fingerprint internally.",
            "inputSchema": {"type": "object", "properties": {
                "role":   {"type": "string", "enum": ["primary", "secondary", "tertiary"]},
                "letter": {"type": "string", "description": "Drive letter (A-Z)"},
                "root":   {"type": "string", "description": "Subfolder name (default: Arcade)", "default": "Arcade"},
            }, "required": ["role", "letter"]},
        },
        {
            "name": "drives_auto",
            "description": "Auto-detect and assign roles by scanning for arcade content. Smart fingerprint-based.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "drives_reconcile",
            "description": "Full reconciliation: re-scan, detect letter changes, discover new drives, heal assignments.",
            "inputSchema": {"type": "object", "properties": {
                "detect_type": {"type": "boolean", "description": "Also detect NVMe/SSD/HDD (slower)", "default": False}
            }},
        },
        {
            "name": "drives_list_indexed",
            "description": "List all indexed drives including disconnected ones. Shows fingerprints and history.",
            "inputSchema": {"type": "object", "properties": {}},
        },
    ]

    def handle(req: dict) -> dict | None:
        method = req.get("method", "")
        rid    = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "drive-manager", "version": "2.0.0"},
            }}
        elif method == "notifications/initialized":
            return None
        elif method == "tools/list":
            return {"jsonrpc": "2.0", "id": rid, "result": {"tools": [
                {"name": t["name"], "description": t["description"],
                 "inputSchema": t["inputSchema"]} for t in TOOLS
            ]}}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {})
            try:
                if name == "drives_scan":
                    result = scan_drives(min_gb=args.get("min_gb", 200))
                elif name == "drives_status":
                    result = drive_status()
                elif name == "drives_set":
                    letter = str(args.get("letter", "")).upper().strip(":\\")
                    role   = args.get("role", "primary")
                    root   = args.get("root", "Arcade")
                    assign_role(role, letter, root)
                    result = {"success": True, "role": role, "letter": letter, "root": root}
                elif name == "drives_auto":
                    st = auto_assign()
                    result = {"success": True, "assignments": {
                        "primary":   st.get("primary"),
                        "secondary": st.get("secondary"),
                        "tertiary":  st.get("tertiary"),
                    }}
                elif name == "drives_reconcile":
                    idx = reconcile(detect_type=args.get("detect_type", False))
                    result = {
                        "success": True,
                        "events": idx.get("events", []),
                        "roles": idx.get("roles", {}),
                        "total_indexed": len(idx.get("drives", {})),
                    }
                elif name == "drives_list_indexed":
                    result = list_indexed_drives()
                else:
                    result = {"error": f"Unknown tool: {name}"}
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": _json.dumps(result, indent=2, default=str)}],
                    "isError": False,
                }}
            except Exception as exc:
                return {"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}\n{traceback.format_exc()}"}],
                    "isError": True,
                }}
        elif method == "ping":
            return {"jsonrpc": "2.0", "id": rid, "result": {}}
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = _json.loads(line)
        except Exception:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(_json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    _mcp_main()
