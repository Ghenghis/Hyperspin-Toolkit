"""Comprehensive audit engine — ROMs, emulators, media, RocketLauncher, HyperSpin XML."""
from __future__ import annotations

import configparser
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db
from engines.scanner import (
    discover_systems, register_systems,
    discover_emulators, register_emulators,
    scan_roms_for_system, parse_hyperspin_xml,
    scan_media_for_system, hash_file, ROM_EXTENSIONS,
)

log = get_logger("auditor")


# ---------------------------------------------------------------------------
# Full ecosystem audit
# ---------------------------------------------------------------------------

def run_full_audit() -> dict[str, Any]:
    """Run a comprehensive audit of the entire HyperSpin ecosystem."""
    log.info("=== Starting full ecosystem audit ===")
    audit("full_audit_start", "ecosystem", {})

    results: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "systems": {},
        "emulators": {},
        "summary": {},
    }

    # 1. Discover and register systems
    systems = discover_systems()
    register_systems(systems)
    results["summary"]["total_systems"] = len(systems)

    # 2. Discover and register emulators
    emulators = discover_emulators()
    register_emulators(emulators)
    results["summary"]["total_emulators"] = len(emulators)
    results["summary"]["healthy_emulators"] = sum(1 for e in emulators if e.get("is_healthy"))

    # 3. Audit each system
    total_roms = 0
    total_games_in_db = 0
    systems_with_xml = 0
    systems_with_roms = 0

    for sys_data in systems:
        sys_name = sys_data["name"]
        sys_result = audit_system(sys_name)
        results["systems"][sys_name] = sys_result

        if sys_result.get("rom_count", 0) > 0:
            systems_with_roms += 1
        total_roms += sys_result.get("rom_count", 0)
        total_games_in_db += sys_result.get("xml_game_count", 0)
        if sys_result.get("has_xml"):
            systems_with_xml += 1

    results["summary"]["total_roms"] = total_roms
    results["summary"]["total_games_in_xml"] = total_games_in_db
    results["summary"]["systems_with_xml"] = systems_with_xml
    results["summary"]["systems_with_roms"] = systems_with_roms

    # 4. Audit RocketLauncher
    results["rocketlauncher"] = audit_rocketlauncher()

    # 5. Calculate ecosystem health score
    results["summary"]["health_score"] = _calculate_health_score(results)

    log.info("=== Full audit complete: %d systems, %d ROMs, %d emulators ===",
             len(systems), total_roms, len(emulators))
    audit("full_audit_complete", "ecosystem", results["summary"])

    return results


# ---------------------------------------------------------------------------
# Per-system audit
# ---------------------------------------------------------------------------

def audit_system(system_name: str) -> dict[str, Any]:
    """Audit a single system: ROMs, XML database, media."""
    hs_root = Path(cfg_get("paths.hyperspin_root", ""))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))

    result: dict[str, Any] = {
        "name": system_name,
        "rom_count": 0,
        "xml_game_count": 0,
        "has_xml": False,
        "media_summary": {},
        "issues": [],
    }

    # Check for XML database
    xml_path = db_root / system_name / f"{system_name}.xml"
    if xml_path.exists():
        result["has_xml"] = True
        games = parse_hyperspin_xml(xml_path)
        result["xml_game_count"] = len(games)
        result["xml_path"] = str(xml_path)
    else:
        result["issues"].append({"severity": "warn", "msg": f"No XML database found for {system_name}"})

    # Scan ROMs — check multiple possible locations
    rom_dirs = [
        hs_root / system_name,
        hs_root / system_name / "roms",
        hs_root / system_name / "ROMs",
    ]
    rom_files: list[dict[str, Any]] = []
    for rom_dir in rom_dirs:
        if rom_dir.exists():
            found = scan_roms_for_system(system_name, rom_dir)
            rom_files.extend(found)
            break

    result["rom_count"] = len(rom_files)

    # Cross-reference ROMs with XML
    if result["has_xml"] and rom_files:
        games = parse_hyperspin_xml(xml_path)
        game_names = {g["name"].lower() for g in games}
        rom_stems = {Path(r["filename"]).stem.lower() for r in rom_files}

        in_xml_not_rom = game_names - rom_stems
        in_rom_not_xml = rom_stems - game_names
        matched = game_names & rom_stems

        result["matched_games"] = len(matched)
        result["missing_roms"] = len(in_xml_not_rom)
        result["extra_roms"] = len(in_rom_not_xml)

        if in_xml_not_rom:
            result["issues"].append({
                "severity": "info",
                "msg": f"{len(in_xml_not_rom)} games in XML but no ROM found"
            })
        if in_rom_not_xml:
            result["issues"].append({
                "severity": "info",
                "msg": f"{len(in_rom_not_xml)} ROMs not in XML database"
            })

    # Scan media
    media = scan_media_for_system(system_name)
    for mtype, items in media.items():
        result["media_summary"][mtype] = len(items)

    # Calculate per-system health
    score = 0.0
    checks = 0
    if result["has_xml"]:
        score += 25
    checks += 25
    if result["rom_count"] > 0:
        score += 25
    checks += 25
    if result.get("matched_games", 0) > 0 and result["xml_game_count"] > 0:
        match_pct = result["matched_games"] / result["xml_game_count"] * 25
        score += match_pct
    checks += 25
    if media:
        score += 25
    checks += 25

    result["health_score"] = round(score, 1)

    # Update database
    try:
        db.execute(
            """UPDATE systems SET rom_count=?, media_count=?, health_score=?,
               last_audit=datetime('now'), updated_at=datetime('now') WHERE name=?""",
            (result["rom_count"], sum(result["media_summary"].values()),
             result["health_score"], system_name)
        )
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Emulator audit
# ---------------------------------------------------------------------------

def audit_emulators() -> list[dict[str, Any]]:
    """Audit all emulators for health and version info."""
    emu_root = Path(cfg_get("paths.emulators_root", ""))
    results: list[dict[str, Any]] = []

    if not emu_root.exists():
        return results

    for entry in sorted(emu_root.iterdir()):
        if not entry.is_dir():
            continue

        emu_result: dict[str, Any] = {
            "name": entry.name,
            "path": str(entry),
            "issues": [],
        }

        # Check for executables
        exes = list(entry.rglob("*.exe"))
        emu_result["exe_count"] = len(exes)
        emu_result["exe_paths"] = [str(e) for e in exes[:5]]

        if not exes:
            emu_result["issues"].append({"severity": "warn", "msg": "No .exe found"})
            emu_result["is_healthy"] = False
        else:
            emu_result["is_healthy"] = True

        # Count total files and size
        files = list(entry.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        total_size = sum(f.stat().st_size for f in files if f.is_file())
        emu_result["file_count"] = file_count
        emu_result["total_size_bytes"] = total_size
        emu_result["total_size_mb"] = round(total_size / (1024 * 1024), 2)

        # Check for config files
        configs = list(entry.rglob("*.ini")) + list(entry.rglob("*.cfg")) + list(entry.rglob("*.conf"))
        emu_result["config_count"] = len(configs)

        results.append(emu_result)

    log.info("Audited %d emulators", len(results))
    return results


# ---------------------------------------------------------------------------
# RocketLauncher audit
# ---------------------------------------------------------------------------

def audit_rocketlauncher() -> dict[str, Any]:
    """Audit RocketLauncher configuration and modules."""
    rl_root = Path(cfg_get("paths.rocketlauncher_root", ""))
    result: dict[str, Any] = {
        "path": str(rl_root),
        "exists": rl_root.exists(),
        "issues": [],
    }

    if not rl_root.exists():
        result["issues"].append({"severity": "error", "msg": "RocketLauncher directory not found"})
        return result

    # Check main executable
    rl_exe = rl_root / "RocketLauncher.exe"
    result["exe_exists"] = rl_exe.exists()

    # Check modules
    modules_dir = rl_root / "Modules"
    if modules_dir.exists():
        modules = [d.name for d in modules_dir.iterdir() if d.is_dir()]
        result["module_count"] = len(modules)
        result["modules"] = modules[:50]
    else:
        result["module_count"] = 0
        result["issues"].append({"severity": "warn", "msg": "No Modules directory found"})

    # Check settings
    settings_dir = rl_root / "Settings"
    if settings_dir.exists():
        ini_files = list(settings_dir.rglob("*.ini"))
        result["settings_file_count"] = len(ini_files)

        # Parse global settings
        global_ini = settings_dir / "RocketLauncher.ini"
        if global_ini.exists():
            try:
                config = configparser.ConfigParser(strict=False)
                config.read(str(global_ini), encoding="utf-8-sig")
                result["rl_sections"] = config.sections()[:20]
            except Exception as exc:
                result["issues"].append({"severity": "warn", "msg": f"Cannot parse RL ini: {exc}"})
    else:
        result["issues"].append({"severity": "warn", "msg": "No Settings directory found"})

    # Check profiles
    profiles_dir = rl_root / "Profiles"
    if profiles_dir.exists():
        result["profile_count"] = sum(1 for _ in profiles_dir.iterdir() if _.is_dir())

    # Check plugins
    plugins_dir = rl_root / "Plugins"
    if plugins_dir.exists():
        result["plugin_count"] = sum(1 for _ in plugins_dir.iterdir() if _.is_dir())

    return result


# ---------------------------------------------------------------------------
# Media completeness audit
# ---------------------------------------------------------------------------

def audit_media_completeness(system_name: str) -> dict[str, Any]:
    """Check media completeness for a system against its XML database."""
    hs_root = Path(cfg_get("paths.hyperspin_root", ""))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))
    media_root = Path(cfg_get("paths.media_root", str(hs_root / "Media")))

    result: dict[str, Any] = {"system": system_name, "media_types": {}}

    # Get game list from XML
    xml_path = db_root / system_name / f"{system_name}.xml"
    if not xml_path.exists():
        result["error"] = "No XML database"
        return result

    games = parse_hyperspin_xml(xml_path)
    game_names = {g["name"] for g in games}
    result["total_games"] = len(game_names)

    # Check each media type
    sys_media = media_root / system_name
    media_checks = {
        "Wheel": sys_media / "Images" / "Wheel",
        "Video": sys_media / "Video",
        "Theme": sys_media / "Themes",
        "Artwork1": sys_media / "Images" / "Artwork1",
        "Artwork2": sys_media / "Images" / "Artwork2",
        "Backgrounds": sys_media / "Images" / "Backgrounds",
    }

    for mtype, mpath in media_checks.items():
        type_result: dict[str, Any] = {"path": str(mpath), "exists": mpath.exists()}

        if mpath.exists():
            files = {f.stem for f in mpath.iterdir() if f.is_file()}
            type_result["file_count"] = len(files)
            matched = game_names & files
            missing = game_names - files
            extra = files - game_names

            type_result["matched"] = len(matched)
            type_result["missing"] = len(missing)
            type_result["extra"] = len(extra)
            type_result["completeness_pct"] = round(
                len(matched) / len(game_names) * 100, 1
            ) if game_names else 0
        else:
            type_result["file_count"] = 0
            type_result["completeness_pct"] = 0

        result["media_types"][mtype] = type_result

    return result


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicate_roms(system_name: str | None = None) -> list[dict[str, Any]]:
    """Find duplicate ROMs by file hash across systems or within one system."""
    hs_root = Path(cfg_get("paths.hyperspin_root", ""))
    hash_map: dict[str, list[str]] = {}

    if system_name:
        systems_to_scan = [system_name]
    else:
        systems = discover_systems()
        systems_to_scan = [s["name"] for s in systems]

    for sys_name in systems_to_scan:
        rom_dir = hs_root / sys_name
        if not rom_dir.exists():
            continue
        for fpath in rom_dir.rglob("*"):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in ROM_EXTENSIONS:
                continue
            file_hash = hash_file(fpath, algorithm="sha256")
            if file_hash:
                if file_hash not in hash_map:
                    hash_map[file_hash] = []
                hash_map[file_hash].append(str(fpath))

    duplicates = [
        {"hash": h, "count": len(paths), "paths": paths}
        for h, paths in hash_map.items()
        if len(paths) > 1
    ]

    log.info("Found %d duplicate ROM groups", len(duplicates))
    return duplicates


# ---------------------------------------------------------------------------
# Health score calculation
# ---------------------------------------------------------------------------

def _calculate_health_score(audit_results: dict[str, Any]) -> float:
    """Calculate overall ecosystem health score (0-100)."""
    summary = audit_results.get("summary", {})
    total_systems = summary.get("total_systems", 0)
    systems_with_roms = summary.get("systems_with_roms", 0)
    systems_with_xml = summary.get("systems_with_xml", 0)
    total_emulators = summary.get("total_emulators", 0)
    healthy_emulators = summary.get("healthy_emulators", 0)

    score = 0.0
    weights = 0.0

    # Systems with ROMs (30%)
    if total_systems > 0:
        score += (systems_with_roms / total_systems) * 30
    weights += 30

    # Systems with XML databases (20%)
    if total_systems > 0:
        score += (systems_with_xml / total_systems) * 20
    weights += 20

    # Emulator health (25%)
    if total_emulators > 0:
        score += (healthy_emulators / total_emulators) * 25
    weights += 25

    # RocketLauncher health (15%)
    rl = audit_results.get("rocketlauncher", {})
    if rl.get("exists") and rl.get("exe_exists"):
        score += 15
    weights += 15

    # Per-system average health (10%)
    system_scores = [
        s.get("health_score", 0)
        for s in audit_results.get("systems", {}).values()
    ]
    if system_scores:
        avg = sum(system_scores) / len(system_scores)
        score += (avg / 100) * 10
    weights += 10

    return round(score, 1)
