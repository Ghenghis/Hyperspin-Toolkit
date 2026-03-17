"""
M64 — Drive Fingerprint Engine
Auto-detect KINHANK HDD variant (A/B/C) from any drive letter based on
directory signatures, key files, and content analysis.
"""

import os
import re
import json
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger("drive_fingerprint")


class KinhankVariant(str, Enum):
    """Known KINHANK HDD product variants."""
    A_HYPERSPIN = "A"          # 12T HyperSpin Attraction (older, Hyperspin-only)
    B_5IN1_ATTRACTION = "B-A"  # 12T 5-in-1 T3 — HyperSpin Attraction (AttractMode) component
    B_5IN1_CORE = "B-C"        # 12T 5-in-1 T3 — CORE - TYPE R (RetroFE) hub component
    C_BATOCERA_BOOT = "C-B"    # 2T Batocera — boot partition
    C_BATOCERA_DATA = "C-D"    # 2T Batocera — data/share partition
    UNKNOWN = "?"              # Not a recognized KINHANK drive


@dataclass
class FrontendInfo:
    """Detected frontend on a drive."""
    name: str
    exe_path: Optional[str] = None
    config_path: Optional[str] = None
    systems_count: int = 0
    games_count: int = 0
    status: str = "detected"  # detected, functional, skeleton, missing


@dataclass
class DriveFingerprint:
    """Complete fingerprint of a KINHANK drive."""
    drive_letter: str
    variant: str = KinhankVariant.UNKNOWN.value
    variant_label: str = "Unknown"
    total_size_gb: float = 0.0
    used_size_gb: float = 0.0
    free_size_gb: float = 0.0
    frontends: List[Dict[str, Any]] = field(default_factory=list)
    systems_total: int = 0
    games_total: int = 0
    pc_games_count: int = 0
    has_game_list: bool = False
    game_list_path: Optional[str] = None
    key_files_found: List[str] = field(default_factory=list)
    key_files_missing: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    is_clone_of: Optional[str] = None
    confidence: float = 0.0  # 0.0-1.0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        lines = [
            f"Drive {self.drive_letter} — {self.variant_label}",
            f"  Variant: {self.variant} (confidence: {self.confidence:.0%})",
            f"  Size: {self.used_size_gb:.1f}GB used / {self.total_size_gb:.1f}GB total",
            f"  Systems: {self.systems_total} | Games: {self.games_total} | PC Games: {self.pc_games_count}",
            f"  Frontends: {len(self.frontends)}",
        ]
        for fe in self.frontends:
            lines.append(f"    - {fe['name']}: {fe['status']} ({fe['systems_count']} systems)")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        if self.is_clone_of:
            lines.append(f"  Clone of: {self.is_clone_of}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Signature definitions for each variant
# ---------------------------------------------------------------------------

VARIANT_A_SIGNATURES = {
    "required": [
        r"Arcade\HyperSpin.exe",
        r"Arcade\Databases",
        r"Arcade\Media",
        r"Arcade\RocketLauncher",
    ],
    "optional": [
        r"Arcade\HyperHQ.exe",
        r"Arcade\Settings",
        r"Arcade\Scripts",
        r"SETUP USER GUIDE - FOR HYPERSPIN",
    ],
}

VARIANT_B_ATTRACTION_SIGNATURES = {
    "required": [
        r"Arcade\collections",
        r"Arcade\romlists",
        r"Arcade\emulators",
    ],
    "distinguishing": [
        r"Arcade\attract.cfg",
        r"Arcade\HyperSpin Attraction.exe",
    ],
    "optional": [
        r"Arcade\layouts",
        r"Arcade\modules",
        r"Arcade\plugins",
        r"Arcade\RocketLauncher",
        r"Arcade\menu-art",
    ],
}

VARIANT_B_CORE_SIGNATURES = {
    "required": [
        r"CORE - TYPE R",
        r"CORE - TYPE R\collections",
    ],
    "distinguishing": [
        r"CORE - TYPE R\CORE.exe",
        r"CORE - TYPE R\settings.conf",
    ],
    "optional": [
        r"Installation",
        r"CORE - TYPE R\collections\COMPUTERS",
        r"CORE - TYPE R\collections\Main",
    ],
}

VARIANT_C_BOOT_SIGNATURES = {
    "required": [
        r"batocera-boot.conf",
    ],
    "optional": [
        r"EFI",
        r"grub",
        r"Game-List",
        r"boot\grub",
    ],
}

VARIANT_C_DATA_SIGNATURES = {
    "required": [
        r"roms",
        r"bios",
    ],
    "optional": [
        r"saves",
        r"themes",
        r"cheats",
        r"decorations",
        r"music",
        r"kodi",
        r"system\batocera.conf",
    ],
}


def _check_path(drive: str, rel_path: str) -> bool:
    """Check if a relative path exists on a drive."""
    full = os.path.join(drive, rel_path)
    return os.path.exists(full)


def _count_dirs(path: str) -> int:
    """Count immediate subdirectories."""
    if not os.path.isdir(path):
        return 0
    try:
        return sum(1 for e in os.scandir(path) if e.is_dir())
    except OSError:
        return 0


def _count_xml_games(db_path: str, system_name: str) -> int:
    """Count <game name= entries in a HyperSpin XML database file."""
    xml_file = os.path.join(db_path, system_name, f"{system_name}.xml")
    if not os.path.isfile(xml_file):
        # Try largest XML in the folder
        sys_dir = os.path.join(db_path, system_name)
        if os.path.isdir(sys_dir):
            xmls = [f for f in os.listdir(sys_dir) if f.endswith(".xml")]
            if xmls:
                xml_file = os.path.join(sys_dir, max(xmls, key=lambda f: os.path.getsize(os.path.join(sys_dir, f))))
            else:
                return 0
        else:
            return 0
    try:
        with open(xml_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return len(re.findall(r"<game name=", content))
    except OSError:
        return 0


def _count_romlist_games(romlist_path: str) -> int:
    """Count game entries in an AttractMode romlist .txt file."""
    if not os.path.isfile(romlist_path):
        return 0
    try:
        with open(romlist_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        # Skip comment/header lines starting with #
        return sum(1 for line in lines if line.strip() and not line.startswith("#"))
    except OSError:
        return 0


def _count_rom_files(rom_dir: str) -> int:
    """Count files in a ROM directory (non-recursive)."""
    if not os.path.isdir(rom_dir):
        return 0
    try:
        return sum(1 for e in os.scandir(rom_dir) if e.is_file())
    except OSError:
        return 0


def _get_drive_sizes(drive: str) -> tuple:
    """Return (total_gb, used_gb, free_gb) for a drive."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(drive)
        return (total / (1024**3), used / (1024**3), free / (1024**3))
    except OSError:
        return (0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Main fingerprint function
# ---------------------------------------------------------------------------

def fingerprint_drive(drive_letter: str) -> DriveFingerprint:
    """
    Analyze a drive and return its KINHANK variant fingerprint.

    Args:
        drive_letter: Drive letter like "D", "D:", or "D:\\"

    Returns:
        DriveFingerprint with variant, frontends, system/game counts, etc.
    """
    # Normalize drive path
    drive = drive_letter.strip().rstrip(":\\")
    drive_root = f"{drive}:\\"

    if not os.path.exists(drive_root):
        fp = DriveFingerprint(drive_letter=f"{drive}:")
        fp.warnings.append(f"Drive {drive}: not accessible")
        return fp

    total, used, free = _get_drive_sizes(drive_root)
    fp = DriveFingerprint(
        drive_letter=f"{drive}:",
        total_size_gb=round(total, 1),
        used_size_gb=round(used, 1),
        free_size_gb=round(free, 1),
    )

    # Track signature matches
    scores = {
        KinhankVariant.A_HYPERSPIN: 0.0,
        KinhankVariant.B_5IN1_ATTRACTION: 0.0,
        KinhankVariant.B_5IN1_CORE: 0.0,
        KinhankVariant.C_BATOCERA_BOOT: 0.0,
        KinhankVariant.C_BATOCERA_DATA: 0.0,
    }

    # --- Check Variant A: HyperSpin Attraction (Older) ---
    a_req = sum(1 for p in VARIANT_A_SIGNATURES["required"] if _check_path(drive_root, p))
    a_opt = sum(1 for p in VARIANT_A_SIGNATURES["optional"] if _check_path(drive_root, p))
    a_total = len(VARIANT_A_SIGNATURES["required"])
    if a_req == a_total:
        scores[KinhankVariant.A_HYPERSPIN] = 0.7 + 0.3 * (a_opt / len(VARIANT_A_SIGNATURES["optional"]))
        for p in VARIANT_A_SIGNATURES["required"]:
            fp.key_files_found.append(p)
    else:
        for p in VARIANT_A_SIGNATURES["required"]:
            if not _check_path(drive_root, p):
                fp.key_files_missing.append(p)

    # --- Check Variant B-A: 5-in-1 Attraction (AttractMode) ---
    ba_req = sum(1 for p in VARIANT_B_ATTRACTION_SIGNATURES["required"] if _check_path(drive_root, p))
    ba_dist = sum(1 for p in VARIANT_B_ATTRACTION_SIGNATURES["distinguishing"] if _check_path(drive_root, p))
    ba_opt = sum(1 for p in VARIANT_B_ATTRACTION_SIGNATURES["optional"] if _check_path(drive_root, p))
    if ba_req == len(VARIANT_B_ATTRACTION_SIGNATURES["required"]) and ba_dist > 0:
        scores[KinhankVariant.B_5IN1_ATTRACTION] = 0.6 + 0.2 * (ba_dist / len(VARIANT_B_ATTRACTION_SIGNATURES["distinguishing"])) + 0.2 * (ba_opt / len(VARIANT_B_ATTRACTION_SIGNATURES["optional"]))
        for p in VARIANT_B_ATTRACTION_SIGNATURES["required"] + VARIANT_B_ATTRACTION_SIGNATURES["distinguishing"]:
            if _check_path(drive_root, p):
                fp.key_files_found.append(p)

    # --- Check Variant B-C: CORE - TYPE R ---
    bc_req = sum(1 for p in VARIANT_B_CORE_SIGNATURES["required"] if _check_path(drive_root, p))
    bc_dist = sum(1 for p in VARIANT_B_CORE_SIGNATURES["distinguishing"] if _check_path(drive_root, p))
    bc_opt = sum(1 for p in VARIANT_B_CORE_SIGNATURES["optional"] if _check_path(drive_root, p))
    if bc_req == len(VARIANT_B_CORE_SIGNATURES["required"]):
        scores[KinhankVariant.B_5IN1_CORE] = 0.5 + 0.3 * (bc_dist / max(1, len(VARIANT_B_CORE_SIGNATURES["distinguishing"]))) + 0.2 * (bc_opt / max(1, len(VARIANT_B_CORE_SIGNATURES["optional"])))
        for p in VARIANT_B_CORE_SIGNATURES["required"] + VARIANT_B_CORE_SIGNATURES["distinguishing"]:
            if _check_path(drive_root, p):
                fp.key_files_found.append(p)

    # --- Check Variant C-B: Batocera Boot ---
    cb_req = sum(1 for p in VARIANT_C_BOOT_SIGNATURES["required"] if _check_path(drive_root, p))
    cb_opt = sum(1 for p in VARIANT_C_BOOT_SIGNATURES["optional"] if _check_path(drive_root, p))
    if cb_req == len(VARIANT_C_BOOT_SIGNATURES["required"]):
        scores[KinhankVariant.C_BATOCERA_BOOT] = 0.7 + 0.3 * (cb_opt / max(1, len(VARIANT_C_BOOT_SIGNATURES["optional"])))
        for p in VARIANT_C_BOOT_SIGNATURES["required"]:
            fp.key_files_found.append(p)

    # --- Check Variant C-D: Batocera Data ---
    cd_req = sum(1 for p in VARIANT_C_DATA_SIGNATURES["required"] if _check_path(drive_root, p))
    cd_opt = sum(1 for p in VARIANT_C_DATA_SIGNATURES["optional"] if _check_path(drive_root, p))
    if cd_req == len(VARIANT_C_DATA_SIGNATURES["required"]):
        scores[KinhankVariant.C_BATOCERA_DATA] = 0.6 + 0.4 * (cd_opt / max(1, len(VARIANT_C_DATA_SIGNATURES["optional"])))
        for p in VARIANT_C_DATA_SIGNATURES["required"]:
            fp.key_files_found.append(p)

    # --- Select best match ---
    best_variant = max(scores, key=scores.get)
    best_score = scores[best_variant]

    if best_score < 0.3:
        fp.variant = KinhankVariant.UNKNOWN.value
        fp.variant_label = "Not a KINHANK drive"
        fp.confidence = 0.0
        return fp

    fp.variant = best_variant.value
    fp.confidence = round(best_score, 2)

    # --- Populate variant-specific details ---
    if best_variant == KinhankVariant.A_HYPERSPIN:
        fp.variant_label = "KINHANK 12T HyperSpin Attraction (Variant A)"
        fp = _analyze_variant_a(fp, drive_root)

    elif best_variant == KinhankVariant.B_5IN1_ATTRACTION:
        fp.variant_label = "KINHANK 12T 5-in-1 T3 — Attraction (Variant B-A)"
        fp = _analyze_variant_b_attraction(fp, drive_root)

    elif best_variant == KinhankVariant.B_5IN1_CORE:
        fp.variant_label = "KINHANK 12T 5-in-1 T3 — CORE Hub (Variant B-C)"
        fp = _analyze_variant_b_core(fp, drive_root)

    elif best_variant == KinhankVariant.C_BATOCERA_BOOT:
        fp.variant_label = "KINHANK 2T Batocera — Boot Partition (Variant C-B)"
        fp = _analyze_variant_c_boot(fp, drive_root)

    elif best_variant == KinhankVariant.C_BATOCERA_DATA:
        fp.variant_label = "KINHANK 2T Batocera — Data Partition (Variant C-D)"
        fp = _analyze_variant_c_data(fp, drive_root)

    # Check for game list files
    _check_game_lists(fp, drive_root)

    return fp


# ---------------------------------------------------------------------------
# Variant-specific analyzers
# ---------------------------------------------------------------------------

def _analyze_variant_a(fp: DriveFingerprint, drive_root: str) -> DriveFingerprint:
    """Analyze Variant A: HyperSpin + RocketLauncher."""
    arcade = os.path.join(drive_root, "Arcade")

    # Count system directories (exclude infrastructure dirs)
    infra_dirs = {
        "cache", "config", "databases", "emulators", "hypersearch",
        "hyperspeech", "hyperspin", "ledblinky", "media", "music",
        "rocketlauncher", "scripts", "settings", "tmp",
    }
    if os.path.isdir(arcade):
        all_dirs = [e.name for e in os.scandir(arcade) if e.is_dir()]
        system_dirs = [d for d in all_dirs if d.lower() not in infra_dirs]
        fp.systems_total = len(system_dirs)

    # Count games from databases
    db_path = os.path.join(arcade, "Databases")
    if os.path.isdir(db_path):
        total_games = 0
        db_systems = [e.name for e in os.scandir(db_path) if e.is_dir()]
        for sys_name in db_systems:
            total_games += _count_xml_games(db_path, sys_name)
        fp.games_total = total_games

    # Frontend info
    hs_exe = os.path.join(arcade, "HyperSpin.exe")
    fe = FrontendInfo(
        name="HyperSpin",
        exe_path=hs_exe if os.path.exists(hs_exe) else None,
        systems_count=fp.systems_total,
        games_count=fp.games_total,
        status="functional" if os.path.exists(hs_exe) else "missing",
    )
    fp.frontends.append(asdict(fe))

    # RocketLauncher
    rl_path = os.path.join(arcade, "RocketLauncher")
    if os.path.isdir(rl_path):
        rl_exe = os.path.join(rl_path, "RocketLauncher.exe")
        rl = FrontendInfo(
            name="RocketLauncher",
            exe_path=rl_exe if os.path.exists(rl_exe) else None,
            status="functional" if os.path.exists(rl_exe) else "detected",
        )
        fp.frontends.append(asdict(rl))

    return fp


def _analyze_variant_b_attraction(fp: DriveFingerprint, drive_root: str) -> DriveFingerprint:
    """Analyze Variant B-A: 5-in-1 AttractMode/HyperSpin Attraction."""
    arcade = os.path.join(drive_root, "Arcade")
    collections = os.path.join(arcade, "collections")

    # Count collections
    if os.path.isdir(collections):
        coll_dirs = [e.name for e in os.scandir(collections) if e.is_dir() and e.name != "Settings"]
        fp.systems_total = len(coll_dirs)

    # Count games from romlists
    romlists = os.path.join(arcade, "romlists")
    if os.path.isdir(romlists):
        total_games = 0
        for entry in os.scandir(romlists):
            if entry.is_file() and entry.name.endswith(".txt"):
                total_games += _count_romlist_games(entry.path)
        fp.games_total = total_games

    # AttractMode frontend
    attract_exe = os.path.join(arcade, "HyperSpin Attraction.exe")
    attract_cfg = os.path.join(arcade, "attract.cfg")
    fe = FrontendInfo(
        name="HyperSpin Attraction (AttractMode)",
        exe_path=attract_exe if os.path.exists(attract_exe) else None,
        config_path=attract_cfg if os.path.exists(attract_cfg) else None,
        systems_count=fp.systems_total,
        games_count=fp.games_total,
        status="functional" if os.path.exists(attract_exe) else "detected",
    )
    fp.frontends.append(asdict(fe))

    # RocketLauncher
    rl_path = os.path.join(arcade, "RocketLauncher")
    if os.path.isdir(rl_path):
        rl = FrontendInfo(name="RocketLauncher", status="detected")
        fp.frontends.append(asdict(rl))

    return fp


def _analyze_variant_b_core(fp: DriveFingerprint, drive_root: str) -> DriveFingerprint:
    """Analyze Variant B-C: CORE - TYPE R (RetroFE launcher hub)."""
    core_path = os.path.join(drive_root, "CORE - TYPE R")
    computers = os.path.join(core_path, "collections", "COMPUTERS", "roms")

    # RetroFE frontend
    core_exe = os.path.join(core_path, "CORE.exe")
    fe = FrontendInfo(
        name="RetroFE (CORE - TYPE R)",
        exe_path=core_exe if os.path.exists(core_exe) else None,
        status="functional" if os.path.exists(core_exe) else "detected",
    )
    fp.frontends.append(asdict(fe))

    # Check embedded frontends
    embedded_frontends = [
        ("HyperSpin Attraction", "collections"),
        ("Hyperspin TeknoParrot", "collections"),
        ("LaunchBox", "Games"),
        ("Playnite", "PC Games"),
        ("RetroBat", "roms"),
        ("Kodi", None),
    ]

    total_systems = 0
    total_games = 0

    for fe_name, content_subdir in embedded_frontends:
        fe_path = os.path.join(computers, fe_name)
        if not os.path.isdir(fe_path):
            continue

        sys_count = 0
        game_count = 0
        status = "skeleton"

        if fe_name == "Playnite" and content_subdir:
            pc_path = os.path.join(fe_path, content_subdir)
            if os.path.isdir(pc_path):
                game_count = _count_dirs(pc_path)
                fp.pc_games_count = game_count
                if game_count > 0:
                    status = "functional"
                    total_games += game_count

        elif fe_name in ("HyperSpin Attraction", "Hyperspin TeknoParrot") and content_subdir:
            coll_path = os.path.join(fe_path, content_subdir)
            if os.path.isdir(coll_path):
                sys_count = _count_dirs(coll_path)
                total_systems += sys_count
                if sys_count > 5:
                    status = "functional"
                elif sys_count > 0:
                    status = "partial"

        elif fe_name == "LaunchBox" and content_subdir:
            games_path = os.path.join(fe_path, content_subdir)
            if os.path.isdir(games_path):
                game_count = _count_dirs(games_path)
                if game_count > 0:
                    status = "functional"
                    total_games += game_count

        elif fe_name == "RetroBat" and content_subdir:
            roms_path = os.path.join(fe_path, content_subdir)
            if os.path.isdir(roms_path):
                sys_count = _count_dirs(roms_path)
                if sys_count > 0:
                    status = "functional"
                    total_systems += sys_count

        elif fe_name == "Kodi":
            status = "detected"

        info = FrontendInfo(
            name=fe_name,
            exe_path=None,
            systems_count=sys_count,
            games_count=game_count,
            status=status,
        )
        fp.frontends.append(asdict(info))

    fp.systems_total = total_systems
    fp.games_total = total_games + fp.pc_games_count

    # Completeness warnings
    functional_count = sum(1 for f in fp.frontends if f["status"] == "functional")
    skeleton_count = sum(1 for f in fp.frontends if f["status"] == "skeleton")
    if skeleton_count > 2:
        fp.warnings.append(f"{skeleton_count} frontends are skeleton installs (no game content)")
    if fp.pc_games_count > 0 and fp.systems_total < 20:
        fp.warnings.append("Drive has mostly PC games with minimal retro content")

    return fp


def _analyze_variant_c_boot(fp: DriveFingerprint, drive_root: str) -> DriveFingerprint:
    """Analyze Variant C-B: Batocera boot partition."""
    fe = FrontendInfo(
        name="Batocera (boot)",
        status="functional" if _check_path(drive_root, "batocera-boot.conf") else "detected",
    )
    fp.frontends.append(asdict(fe))
    return fp


def _analyze_variant_c_data(fp: DriveFingerprint, drive_root: str) -> DriveFingerprint:
    """Analyze Variant C-D: Batocera data/share partition."""
    roms_path = os.path.join(drive_root, "roms")
    if os.path.isdir(roms_path):
        sys_dirs = [e.name for e in os.scandir(roms_path) if e.is_dir()]
        fp.systems_total = len(sys_dirs)

        # Count total ROM files across first 30 systems for speed
        total_roms = 0
        for sys_name in sys_dirs[:30]:
            sys_path = os.path.join(roms_path, sys_name)
            total_roms += _count_rom_files(sys_path)
        fp.games_total = total_roms  # approximate

    fe = FrontendInfo(
        name="Batocera / EmulationStation",
        systems_count=fp.systems_total,
        games_count=fp.games_total,
        status="functional",
    )
    fp.frontends.append(asdict(fe))

    # Check for BIOS
    bios_path = os.path.join(drive_root, "bios")
    if os.path.isdir(bios_path):
        bios_count = sum(1 for e in os.scandir(bios_path) if e.is_file())
        if bios_count > 0:
            fp.key_files_found.append(f"bios/ ({bios_count} files)")

    return fp


def _check_game_lists(fp: DriveFingerprint, drive_root: str) -> None:
    """Check for game list files on the drive."""
    patterns = ["Game-List", "Game List", "GameList", "game_list", "gamelist"]
    for pattern in patterns:
        for entry in os.scandir(drive_root):
            if pattern.lower() in entry.name.lower():
                fp.has_game_list = True
                fp.game_list_path = entry.path
                return
        # Check one level deep in known locations
        for subdir in ["Arcade", "CORE - TYPE R"]:
            check = os.path.join(drive_root, subdir)
            if os.path.isdir(check):
                try:
                    for entry in os.scandir(check):
                        if pattern.lower() in entry.name.lower():
                            fp.has_game_list = True
                            fp.game_list_path = entry.path
                            return
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Multi-drive scanning & clone detection
# ---------------------------------------------------------------------------

def fingerprint_all_drives() -> List[DriveFingerprint]:
    """Scan all available drive letters and fingerprint KINHANK drives."""
    results = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive_root = f"{letter}:\\"
        if os.path.exists(drive_root):
            fp = fingerprint_drive(letter)
            if fp.variant != KinhankVariant.UNKNOWN.value:
                results.append(fp)
    return results


def detect_clones(fingerprints: List[DriveFingerprint]) -> List[DriveFingerprint]:
    """Detect clone drives by comparing system counts and variant types."""
    # Group by variant
    by_variant = {}
    for fp in fingerprints:
        key = fp.variant
        by_variant.setdefault(key, []).append(fp)

    for variant, fps in by_variant.items():
        if len(fps) < 2:
            continue
        # Compare system counts within same variant
        for i, fp1 in enumerate(fps):
            for fp2 in fps[i + 1:]:
                if fp1.systems_total == fp2.systems_total and fp1.systems_total > 0:
                    # Same variant, same system count — likely clones
                    fp2.is_clone_of = fp1.drive_letter
                    fp2.warnings.append(f"Possible clone of {fp1.drive_letter} (same {fp1.systems_total} systems)")

    return fingerprints


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            fp = fingerprint_drive(arg)
            print(fp.summary())
            print()
    else:
        print("Scanning all drives...")
        results = fingerprint_all_drives()
        results = detect_clones(results)
        for fp in results:
            print(fp.summary())
            print()
        if not results:
            print("No KINHANK drives detected.")
