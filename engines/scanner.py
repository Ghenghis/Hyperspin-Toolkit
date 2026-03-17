"""Filesystem scanner engine — discovers systems, ROMs, emulators, media."""
from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger, audit
from core import database as db

log = get_logger("scanner")


# ---------------------------------------------------------------------------
# System discovery
# ---------------------------------------------------------------------------

def discover_systems() -> list[dict[str, Any]]:
    """Scan HyperSpin root and register every system folder."""
    hs_root = Path(cfg_get("paths.hyperspin_root", ""))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))
    media_root = Path(cfg_get("paths.media_root", str(hs_root / "Media")))

    skip = {
        "emulators", "rocketlauncher", "media", "databases", "settings",
        "config", "scripts", "cache", "tmp", "hypersearch", "hyperspeech",
        "hyperspin startup script", "ledblinky", "jukebox",
        "music (put your music here)", "magazines",
    }

    systems: list[dict[str, Any]] = []
    if not hs_root.exists():
        log.error("HyperSpin root not found: %s", hs_root)
        return systems

    for entry in sorted(hs_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.lower() in skip:
            continue

        name = entry.name
        xml_path = db_root / name / f"{name}.xml"
        media_path = media_root / name

        sys_data = {
            "name": name,
            "folder_name": name,
            "xml_path": str(xml_path) if xml_path.exists() else None,
            "media_path": str(media_path) if media_path.exists() else None,
        }
        systems.append(sys_data)

    log.info("Discovered %d systems under %s", len(systems), hs_root)
    return systems


def register_systems(systems: list[dict[str, Any]]) -> int:
    """Insert or update discovered systems in the database."""
    count = 0
    for sys_data in systems:
        try:
            existing = db.execute(
                "SELECT id FROM systems WHERE name = ?", (sys_data["name"],)
            )
            if existing:
                db.execute(
                    "UPDATE systems SET folder_name=?, xml_path=?, media_path=?, updated_at=datetime('now') WHERE name=?",
                    (sys_data["folder_name"], sys_data.get("xml_path"), sys_data.get("media_path"), sys_data["name"])
                )
            else:
                db.insert("systems", sys_data)
            count += 1
        except Exception as exc:
            log.warning("Failed to register system %s: %s", sys_data["name"], exc)
    audit("systems_registered", "database", {"count": count})
    return count


# ---------------------------------------------------------------------------
# Emulator discovery
# ---------------------------------------------------------------------------

def discover_emulators() -> list[dict[str, Any]]:
    """Scan the emulators directory and catalog each one."""
    emu_root = Path(cfg_get("paths.emulators_root", ""))
    emulators: list[dict[str, Any]] = []

    if not emu_root.exists():
        log.error("Emulators root not found: %s", emu_root)
        return emulators

    for entry in sorted(emu_root.iterdir()):
        if not entry.is_dir():
            continue

        exe_candidates = list(entry.glob("*.exe"))
        exe_path = str(exe_candidates[0]) if exe_candidates else None

        emulators.append({
            "name": entry.name,
            "folder_name": entry.name,
            "exe_path": exe_path,
            "is_healthy": 1 if exe_path and Path(exe_path).exists() else 0,
        })

    log.info("Discovered %d emulators under %s", len(emulators), emu_root)
    return emulators


def register_emulators(emulators: list[dict[str, Any]]) -> int:
    """Insert or update discovered emulators in the database."""
    count = 0
    for emu in emulators:
        try:
            existing = db.execute("SELECT id FROM emulators WHERE name = ?", (emu["name"],))
            if existing:
                db.execute(
                    "UPDATE emulators SET exe_path=?, is_healthy=?, updated_at=datetime('now') WHERE name=?",
                    (emu.get("exe_path"), emu.get("is_healthy", 0), emu["name"])
                )
            else:
                db.insert("emulators", emu)
            count += 1
        except Exception as exc:
            log.warning("Failed to register emulator %s: %s", emu["name"], exc)
    audit("emulators_registered", "database", {"count": count})
    return count


# ---------------------------------------------------------------------------
# ROM scanning
# ---------------------------------------------------------------------------

ROM_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".bin", ".cue", ".iso", ".img", ".chd",
    ".nes", ".smc", ".sfc", ".gba", ".gbc", ".gb", ".nds", ".3ds",
    ".n64", ".z64", ".v64", ".gcm", ".wbfs", ".nsp", ".xci",
    ".gen", ".md", ".smd", ".gg", ".sms", ".32x", ".cdi", ".gdi",
    ".a26", ".a52", ".a78", ".lnx", ".jag", ".j64",
    ".pce", ".sgx", ".ngp", ".ngc", ".ws", ".wsc",
    ".pbp", ".cso", ".pkg", ".xex", ".xbe",
    ".rom", ".col", ".int", ".vec",
    ".d64", ".t64", ".tap", ".crt", ".prg",
    ".adf", ".dms", ".hdf",
    ".dsk", ".cas", ".mx1", ".mx2",
    ".swf", ".fla",
}


def scan_roms_for_system(system_name: str, rom_dir: Path) -> list[dict[str, Any]]:
    """Scan a ROM directory and return file info for all ROMs."""
    roms: list[dict[str, Any]] = []
    if not rom_dir.exists():
        return roms

    for fpath in rom_dir.rglob("*"):
        if not fpath.is_file():
            continue
        ext = fpath.suffix.lower()
        if ext not in ROM_EXTENSIONS:
            continue
        roms.append({
            "filename": fpath.name,
            "filepath": str(fpath),
            "size_bytes": fpath.stat().st_size,
            "extension": ext,
        })
    return roms


# ---------------------------------------------------------------------------
# HyperSpin XML parsing
# ---------------------------------------------------------------------------

def parse_hyperspin_xml(xml_path: str | Path) -> list[dict[str, str]]:
    """Parse a HyperSpin system XML database file and return game entries."""
    games: list[dict[str, str]] = []
    xml_path = Path(xml_path)
    if not xml_path.exists():
        return games

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        for game_el in root.iter("game"):
            name = game_el.get("name", "")
            desc_el = game_el.find("description")
            year_el = game_el.find("year")
            mfg_el = game_el.find("manufacturer")
            genre_el = game_el.find("genre")
            rating_el = game_el.find("rating")

            games.append({
                "name": name,
                "description": desc_el.text if desc_el is not None and desc_el.text else name,
                "year": year_el.text if year_el is not None and year_el.text else "",
                "manufacturer": mfg_el.text if mfg_el is not None and mfg_el.text else "",
                "genre": genre_el.text if genre_el is not None and genre_el.text else "",
                "rating": rating_el.text if rating_el is not None and rating_el.text else "",
            })
    except ET.ParseError as exc:
        log.error("XML parse error in %s: %s", xml_path, exc)
    except Exception as exc:
        log.error("Failed to parse %s: %s", xml_path, exc)

    return games


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------

def hash_file(filepath: str | Path, algorithm: str = "sha256") -> str | None:
    """Compute hash of a file. Returns hex string or None on error."""
    try:
        h = hashlib.new(algorithm)
        with open(filepath, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)  # 1MB chunks
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception as exc:
        log.warning("Hash failed for %s: %s", filepath, exc)
        return None


# ---------------------------------------------------------------------------
# Media scanning
# ---------------------------------------------------------------------------

MEDIA_TYPES = {
    "Images": {"Artwork1", "Artwork2", "Artwork3", "Artwork4",
               "Backgrounds", "GenreBackgrounds", "GenreWheel",
               "Letters", "Other", "Pointer", "Special", "Wheel"},
    "Video": {"Video"},
    "Themes": {"Themes"},
    "Sounds": {"Sound"},
}


def scan_media_for_system(system_name: str) -> dict[str, list[dict[str, Any]]]:
    """Scan media folders for a system. Returns {media_type: [file_info]}."""
    media_root = Path(cfg_get("paths.media_root", ""))
    sys_media = media_root / system_name
    result: dict[str, list[dict[str, Any]]] = {}

    if not sys_media.exists():
        return result

    for category, folders in MEDIA_TYPES.items():
        for folder_name in folders:
            folder = sys_media / category / folder_name if category != "Themes" else sys_media / folder_name
            # Try alternate paths
            candidates = [
                sys_media / category / folder_name,
                sys_media / folder_name,
            ]
            for candidate in candidates:
                if candidate.exists() and candidate.is_dir():
                    items = []
                    for f in candidate.iterdir():
                        if f.is_file():
                            items.append({
                                "game_name": f.stem,
                                "media_type": folder_name.lower(),
                                "filepath": str(f),
                                "size_bytes": f.stat().st_size,
                            })
                    if items:
                        key = f"{category}/{folder_name}"
                        result[key] = items
                    break

    return result
