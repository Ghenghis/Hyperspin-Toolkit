"""Media Asset Auditor — scan for missing, corrupt, and orphaned media.

Milestone M8: Verify that every game in each system's XML database has the
required media assets (wheel art, video snap, theme, box art, etc.) and flag
missing or corrupt files.

Reports per system:
  - coverage %  per media type
  - missing     games without a required asset
  - corrupt     files that fail image/video header validation
  - orphaned    media files with no matching game in the XML
  - oversized   media files exceeding expected size thresholds
"""
from __future__ import annotations

import os
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit

log = get_logger("media_auditor")


# ═══════════════════════════════════════════════════════════════════════
# Media type definitions
# ═══════════════════════════════════════════════════════════════════════

# Required media types and their folder paths relative to Media/<system>/
MEDIA_TYPES: dict[str, dict[str, Any]] = {
    "wheel": {
        "paths": ["Images/Wheel"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".apng", ".webp"},
        "required": True,
        "max_size_mb": 5,
    },
    "video": {
        "paths": ["Video"],
        "extensions": {".mp4", ".flv", ".avi", ".mkv", ".wmv", ".f4v"},
        "required": True,
        "max_size_mb": 200,
    },
    "theme": {
        "paths": ["Themes"],
        "extensions": {".zip", ".7z"},
        "required": False,
        "max_size_mb": 50,
    },
    "artwork1": {
        "paths": ["Images/Artwork1"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        "required": False,
        "max_size_mb": 10,
    },
    "artwork2": {
        "paths": ["Images/Artwork2"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        "required": False,
        "max_size_mb": 10,
    },
    "artwork3": {
        "paths": ["Images/Artwork3"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        "required": False,
        "max_size_mb": 10,
    },
    "artwork4": {
        "paths": ["Images/Artwork4"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        "required": False,
        "max_size_mb": 10,
    },
    "background": {
        "paths": ["Images/Backgrounds"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif", ".webp"},
        "required": False,
        "max_size_mb": 15,
    },
    "sound": {
        "paths": ["Sound"],
        "extensions": {".mp3", ".wav", ".ogg", ".flac"},
        "required": False,
        "max_size_mb": 20,
    },
}

# Magic bytes for image/video header validation
IMAGE_SIGNATURES: dict[str, list[bytes]] = {
    ".png":  [b"\x89PNG\r\n\x1a\n"],
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif":  [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".bmp":  [b"BM"],
}

VIDEO_SIGNATURES: dict[str, list[bytes]] = {
    ".mp4": [b"\x00\x00\x00", b"ftyp"],
    ".flv": [b"FLV"],
    ".avi": [b"RIFF"],
    ".mkv": [b"\x1a\x45\xdf\xa3"],
    ".wmv": [b"\x30\x26\xb2\x75"],
}


# ═══════════════════════════════════════════════════════════════════════
# Corruption detection
# ═══════════════════════════════════════════════════════════════════════

def is_corrupt_image(filepath: Path) -> bool:
    """Check if an image file has a valid header signature."""
    ext = filepath.suffix.lower()
    sigs = IMAGE_SIGNATURES.get(ext)
    if not sigs:
        return False  # Unknown format, don't flag

    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        if len(header) < 3:
            return True  # Too small to be valid
        return not any(header.startswith(sig) for sig in sigs)
    except (OSError, PermissionError):
        return True


def is_corrupt_video(filepath: Path) -> bool:
    """Check if a video file has a valid header signature."""
    ext = filepath.suffix.lower()
    sigs = VIDEO_SIGNATURES.get(ext)
    if not sigs:
        return False

    try:
        with open(filepath, "rb") as f:
            header = f.read(16)
        if len(header) < 4:
            return True
        # MP4 is special: ftyp can appear at offset 4
        if ext == ".mp4":
            return not (header[4:8] == b"ftyp" or header[:3] == b"\x00\x00\x00")
        return not any(header.startswith(sig) for sig in sigs)
    except (OSError, PermissionError):
        return True


def is_corrupt_file(filepath: Path) -> bool:
    """Check if a media file appears corrupt based on header validation."""
    ext = filepath.suffix.lower()
    if ext in IMAGE_SIGNATURES:
        return is_corrupt_image(filepath)
    if ext in VIDEO_SIGNATURES:
        return is_corrupt_video(filepath)
    # Zero-byte files are always corrupt
    try:
        return filepath.stat().st_size == 0
    except OSError:
        return True


# ═══════════════════════════════════════════════════════════════════════
# Game list extraction
# ═══════════════════════════════════════════════════════════════════════

def _get_game_names_from_xml(xml_path: Path) -> list[str]:
    """Extract game names from a HyperSpin XML database."""
    import xml.etree.ElementTree as ET
    names: list[str] = []
    if not xml_path.exists():
        return names
    try:
        tree = ET.parse(str(xml_path))
        for game_el in tree.getroot().iter("game"):
            name = game_el.get("name", "")
            if name:
                names.append(name)
    except Exception as exc:
        log.warning("Failed to parse XML %s: %s", xml_path, exc)
    return names


# ═══════════════════════════════════════════════════════════════════════
# Single-system media audit
# ═══════════════════════════════════════════════════════════════════════

def audit_media_for_system(
    system_name: str,
    *,
    check_corruption: bool = True,
    check_orphans: bool = True,
    check_oversized: bool = True,
) -> dict[str, Any]:
    """Audit media completeness for a single system.

    Args:
        system_name:      System name matching HyperSpin folder.
        check_corruption: Validate file headers for known formats.
        check_orphans:    Flag media with no matching game in XML.
        check_oversized:  Flag files exceeding size thresholds.

    Returns:
        {
          "system": str,
          "game_count": int,
          "media_types": {type: {coverage_pct, missing, corrupt, orphaned, oversized, ...}},
          "overall_coverage_pct": float,
          "issues": [{severity, type, game, media_type, path, detail}],
          "summary": {total_missing, total_corrupt, total_orphaned, total_oversized},
        }
    """
    hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    media_root = Path(cfg_get("paths.media_root", str(hs_root / "Media")))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))

    sys_media = media_root / system_name
    xml_path = db_root / system_name / f"{system_name}.xml"

    result: dict[str, Any] = {
        "system": system_name,
        "media_root": str(sys_media),
        "xml_path": str(xml_path),
        "game_count": 0,
        "media_types": {},
        "issues": [],
        "overall_coverage_pct": 0.0,
        "summary": {
            "total_missing": 0,
            "total_corrupt": 0,
            "total_orphaned": 0,
            "total_oversized": 0,
        },
    }

    # Get game list
    game_names = _get_game_names_from_xml(xml_path)
    game_set = set(game_names)
    result["game_count"] = len(game_names)

    if not game_names:
        result["issues"].append({
            "severity": "warn",
            "type": "no_games",
            "detail": f"No games found in XML: {xml_path}",
        })
        return result

    coverage_scores: list[float] = []

    for media_type, mdef in MEDIA_TYPES.items():
        type_result: dict[str, Any] = {
            "total_files": 0,
            "coverage_pct": 0.0,
            "missing_count": 0,
            "missing_games": [],
            "corrupt_count": 0,
            "corrupt_files": [],
            "orphaned_count": 0,
            "orphaned_files": [],
            "oversized_count": 0,
            "oversized_files": [],
        }

        # Find the media folder
        media_folder: Optional[Path] = None
        for rel_path in mdef["paths"]:
            candidate = sys_media / rel_path
            if candidate.exists():
                media_folder = candidate
                break

        if media_folder is None:
            # Entire media type folder missing
            type_result["missing_count"] = len(game_names) if mdef["required"] else 0
            if mdef["required"]:
                type_result["missing_games"] = game_names[:50]
                result["issues"].append({
                    "severity": "error" if mdef["required"] else "info",
                    "type": "folder_missing",
                    "media_type": media_type,
                    "detail": f"Media folder not found for {media_type}",
                })
            result["media_types"][media_type] = type_result
            if mdef["required"]:
                coverage_scores.append(0.0)
            continue

        # Index media files by stem (game name)
        media_by_stem: dict[str, Path] = {}
        all_files: list[Path] = []
        for fpath in media_folder.iterdir():
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in mdef["extensions"]:
                continue
            all_files.append(fpath)
            media_by_stem[fpath.stem] = fpath

        type_result["total_files"] = len(all_files)

        # Check missing
        found = 0
        for game in game_names:
            if game in media_by_stem:
                found += 1
            else:
                type_result["missing_count"] += 1
                if len(type_result["missing_games"]) < 50:
                    type_result["missing_games"].append(game)
                if mdef["required"]:
                    result["issues"].append({
                        "severity": "warn",
                        "type": "missing",
                        "game": game,
                        "media_type": media_type,
                        "detail": f"Missing {media_type} for {game}",
                    })

        coverage = round(found / len(game_names) * 100, 1) if game_names else 0
        type_result["coverage_pct"] = coverage
        if mdef["required"]:
            coverage_scores.append(coverage)

        # Check corruption
        if check_corruption:
            for fpath in all_files:
                if is_corrupt_file(fpath):
                    type_result["corrupt_count"] += 1
                    if len(type_result["corrupt_files"]) < 50:
                        type_result["corrupt_files"].append(str(fpath))
                    result["issues"].append({
                        "severity": "error",
                        "type": "corrupt",
                        "game": fpath.stem,
                        "media_type": media_type,
                        "path": str(fpath),
                        "detail": f"Corrupt {media_type}: {fpath.name}",
                    })

        # Check orphans
        if check_orphans:
            for stem, fpath in media_by_stem.items():
                if stem not in game_set:
                    type_result["orphaned_count"] += 1
                    if len(type_result["orphaned_files"]) < 50:
                        type_result["orphaned_files"].append(str(fpath))
                    result["issues"].append({
                        "severity": "info",
                        "type": "orphaned",
                        "game": stem,
                        "media_type": media_type,
                        "path": str(fpath),
                        "detail": f"Orphaned {media_type}: no game '{stem}' in XML",
                    })

        # Check oversized
        if check_oversized:
            max_bytes = mdef["max_size_mb"] * 1024 * 1024
            for fpath in all_files:
                try:
                    size = fpath.stat().st_size
                    if size > max_bytes:
                        type_result["oversized_count"] += 1
                        size_mb = round(size / (1024 * 1024), 1)
                        if len(type_result["oversized_files"]) < 50:
                            type_result["oversized_files"].append({
                                "path": str(fpath),
                                "size_mb": size_mb,
                            })
                        result["issues"].append({
                            "severity": "info",
                            "type": "oversized",
                            "game": fpath.stem,
                            "media_type": media_type,
                            "path": str(fpath),
                            "detail": f"Oversized {media_type}: {size_mb} MB (max {mdef['max_size_mb']} MB)",
                        })
                except OSError:
                    pass

        result["media_types"][media_type] = type_result

    # Overall coverage (required types only)
    result["overall_coverage_pct"] = round(
        sum(coverage_scores) / len(coverage_scores), 1
    ) if coverage_scores else 0.0

    # Summary counts
    for mtype_result in result["media_types"].values():
        result["summary"]["total_missing"] += mtype_result["missing_count"]
        result["summary"]["total_corrupt"] += mtype_result["corrupt_count"]
        result["summary"]["total_orphaned"] += mtype_result["orphaned_count"]
        result["summary"]["total_oversized"] += mtype_result["oversized_count"]

    log.info(
        "Media audit: %s — games=%d coverage=%.1f%% missing=%d corrupt=%d orphans=%d",
        system_name, result["game_count"], result["overall_coverage_pct"],
        result["summary"]["total_missing"], result["summary"]["total_corrupt"],
        result["summary"]["total_orphaned"],
    )

    audit("media_audit", system_name, {
        k: v for k, v in result.items() if k not in ("issues", "media_types")
    })

    return result


# ═══════════════════════════════════════════════════════════════════════
# Batch audit
# ═══════════════════════════════════════════════════════════════════════

def audit_all_media(
    *,
    check_corruption: bool = True,
    check_orphans: bool = True,
    check_oversized: bool = True,
) -> dict[str, Any]:
    """Audit media for all discovered systems.

    Returns:
        {
          "systems": {name: audit_result (without full issue lists)},
          "systems_checked": int,
          "avg_coverage_pct": float,
          "total_missing": int,
          "total_corrupt": int,
          "total_orphaned": int,
          "worst_systems": [{name, coverage_pct}],
        }
    """
    hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))

    results: dict[str, Any] = {"systems": {}}
    coverages: list[float] = []
    totals = {"total_missing": 0, "total_corrupt": 0, "total_orphaned": 0, "total_oversized": 0}

    if not db_root.exists():
        return {**results, "error": f"Databases root not found: {db_root}"}

    # Find systems with XML databases
    for sys_dir in sorted(db_root.iterdir()):
        if not sys_dir.is_dir():
            continue
        xml_file = sys_dir / f"{sys_dir.name}.xml"
        if not xml_file.exists():
            continue

        system_name = sys_dir.name
        audit_result = audit_media_for_system(
            system_name,
            check_corruption=check_corruption,
            check_orphans=check_orphans,
            check_oversized=check_oversized,
        )

        # Store compact summary (no full issue lists)
        compact = {
            k: v for k, v in audit_result.items() if k != "issues"
        }
        # Trim media_types to just coverage and counts
        for mt, mt_data in compact.get("media_types", {}).items():
            for trim_key in ("missing_games", "corrupt_files", "orphaned_files", "oversized_files"):
                if trim_key in mt_data:
                    mt_data[trim_key] = mt_data[trim_key][:5]

        results["systems"][system_name] = compact
        coverages.append(audit_result["overall_coverage_pct"])
        for key in totals:
            totals[key] += audit_result["summary"].get(key, 0)

    results["systems_checked"] = len(results["systems"])
    results["avg_coverage_pct"] = round(
        sum(coverages) / len(coverages), 1
    ) if coverages else 0.0
    results.update(totals)

    # Worst systems
    worst = sorted(
        [(name, data["overall_coverage_pct"]) for name, data in results["systems"].items()],
        key=lambda x: x[1],
    )[:10]
    results["worst_systems"] = [{"name": n, "coverage_pct": c} for n, c in worst]

    log.info(
        "Batch media audit: %d systems, avg_coverage=%.1f%%, missing=%d, corrupt=%d",
        results["systems_checked"], results["avg_coverage_pct"],
        totals["total_missing"], totals["total_corrupt"],
    )

    return results
