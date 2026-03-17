"""M55 — BIOS Management & Verification System.

Scans emulator directories for BIOS files, verifies checksums against
known-good hashes (libretro System.dat / community databases), detects
missing required BIOS files, and reports per-system BIOS health.

Supports:
  - RetroArch system/ directory scanning
  - Per-emulator BIOS directory scanning
  - MD5 checksum verification against known-good database
  - Missing BIOS detection per system/core
  - BIOS health reporting (present/valid, wrong checksum, missing)
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("bios_manager")


# ═══════════════════════════════════════════════════════════════════════
# Known BIOS Database
# ═══════════════════════════════════════════════════════════════════════
# Maps system name → list of BIOS entries.  Each entry has:
#   filename:  expected filename
#   md5:       known-good MD5 hash (lowercase hex)
#   required:  whether the BIOS is mandatory for the system to work
#   desc:      human-readable description
#
# Sources: libretro System.dat, Batocera es_bios.xml, RetroArch docs,
#          community verified hashes from No-Intro / Redump.

@dataclass
class BiosEntry:
    """Definition of a single expected BIOS file."""
    filename: str
    md5: str
    required: bool = True
    desc: str = ""
    system: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "md5": self.md5,
            "required": self.required,
            "desc": self.desc,
            "system": self.system,
        }


# Comprehensive BIOS database — covers most common retro systems
# MD5 hashes are from widely-published community verification sets
KNOWN_BIOS: dict[str, list[BiosEntry]] = {
    "PlayStation": [
        BiosEntry("scph5500.bin", "8dd7d5296a650fac7319bce665a6a53c", True,  "PS1 BIOS (Japan v3.0 01/06/97)"),
        BiosEntry("scph5501.bin", "490f666e1afb15b7571ff3f97f93b789", True,  "PS1 BIOS (USA v3.0 11/18/96)"),
        BiosEntry("scph5502.bin", "32736f17079d0b2b7024407c39bd3050", True,  "PS1 BIOS (Europe v3.0 01/06/97)"),
        BiosEntry("scph1001.bin", "924e392ed05558ffdb115408c263dccf", False, "PS1 BIOS (USA v2.2 12/04/95)"),
        BiosEntry("scph7001.bin", "1e68c231d0896b7eadcad1d7d8e76129", False, "PS1 BIOS (USA v4.1 12/16/97)"),
    ],
    "PlayStation 2": [
        BiosEntry("ps2-0230a-20080220.bin", "7f5bb1d0e0e59303c00399a1ec14d70e", True,  "PS2 BIOS v2.30 (USA)"),
        BiosEntry("ps2-0220a-20060905.bin", "1c6cd0e3eb6b0ee4e8cb4ab5e1360f3e", False, "PS2 BIOS v2.20 (USA)"),
        BiosEntry("SCPH-70012_BIOS_V12_USA_200.BIN", "", False, "PS2 BIOS v1.2 (USA Slim)"),
    ],
    "Sega Saturn": [
        BiosEntry("sega_101.bin",  "85ec9ca47d8f6807718151cbcbf8b689", True,  "Saturn BIOS (USA)"),
        BiosEntry("mpr-17933.bin", "3240872c70984b6cbfda1586cab68dbe", True,  "Saturn BIOS (Europe)"),
        BiosEntry("mpr-17932.bin", "255113ba943c92a54facd25a10fd780c", False, "Saturn BIOS (Japan)"),
    ],
    "Sega Dreamcast": [
        BiosEntry("dc_boot.bin",  "e10c53c2f8b90bab96ead2d368858623", True,  "Dreamcast BIOS"),
        BiosEntry("dc_flash.bin", "0a93f7940c455905bea6e392dfde92a4", True,  "Dreamcast Flash ROM"),
    ],
    "Sega CD": [
        BiosEntry("bios_CD_U.bin", "2efd74e3232ff260e371b99f84024f7f", True,  "Sega CD BIOS (USA)"),
        BiosEntry("bios_CD_E.bin", "e66fa1dc5820d254611fdcdba0662372", True,  "Sega CD BIOS (Europe)"),
        BiosEntry("bios_CD_J.bin", "278a9397d192149e84e820ac621a8edd", False, "Sega CD BIOS (Japan)"),
    ],
    "Neo Geo": [
        BiosEntry("neogeo.zip", "", True, "Neo Geo BIOS (archive with multiple ROMs)"),
    ],
    "Neo Geo CD": [
        BiosEntry("neocdz.zip", "", True,  "Neo Geo CDZ BIOS"),
        BiosEntry("neocd_f.rom", "f39572af7584cb5b3f70ae8cc848aba2", False, "Neo Geo CD Front Loader BIOS"),
        BiosEntry("neocd_sf.rom", "11526d58d4c524daef7d5f67f9e578d6", False, "Neo Geo CD Top Loader BIOS"),
        BiosEntry("neocd_t.rom", "de3cf45d227ad44645b22571ef99c014", False, "Neo Geo CDZ BIOS"),
        BiosEntry("neocd_st.rom", "f6325a33c6d63ea4b9162a3fa8c32727", False, "Neo Geo CDZ (alt) BIOS"),
    ],
    "Game Boy Advance": [
        BiosEntry("gba_bios.bin", "a860e8c0b6d573d191e4ec7db1b1e4f6", True, "GBA BIOS"),
    ],
    "Game Boy": [
        BiosEntry("gb_bios.bin",  "32fbbd84168d3482956eb3c5051637f5", False, "Game Boy BIOS (optional for most cores)"),
        BiosEntry("gbc_bios.bin", "dbfce9db9deaa2567f6a84fde55f9680", False, "Game Boy Color BIOS"),
    ],
    "Nintendo DS": [
        BiosEntry("bios7.bin",   "df692a80a5b1bc90728bc3dfc76cd948", True,  "NDS ARM7 BIOS"),
        BiosEntry("bios9.bin",   "a392174eb3e572fed6447e956bde4b25", True,  "NDS ARM9 BIOS"),
        BiosEntry("firmware.bin", "145eaef5bd3037cbc247c213bb3da1b3", True,  "NDS Firmware"),
    ],
    "TurboGrafx-CD": [
        BiosEntry("syscard3.pce", "ff1a674273fe3540ccef576376b7e26c", True, "TurboGrafx CD System Card 3.0"),
        BiosEntry("syscard1.pce", "2b7ccb3d86baa18f6eab99b22c3ee1e2", False, "TurboGrafx CD System Card 1.0"),
    ],
    "Atari 5200": [
        BiosEntry("5200.rom", "281f20ea4320404ec820fb7ec0693b38", True, "Atari 5200 BIOS"),
    ],
    "Atari 7800": [
        BiosEntry("7800 BIOS (U).rom", "0763f1ffb006ddbe32e52d497ee848ae", True, "Atari 7800 BIOS"),
    ],
    "Atari Lynx": [
        BiosEntry("lynxboot.img", "fcd403db69f54290b51035d82f835e7b", True, "Atari Lynx Boot ROM"),
    ],
    "ColecoVision": [
        BiosEntry("colecovision.rom", "2c66f5911e5b42b8ebe113403548eee7", True, "ColecoVision BIOS"),
    ],
    "Intellivision": [
        BiosEntry("exec.bin", "62e761035cb657903761800f4437b8af", True,  "Intellivision Executive ROM"),
        BiosEntry("grom.bin", "0cd5946c6473e42e8e4c2137785e427f", True,  "Intellivision Graphics ROM"),
    ],
    "MSX": [
        BiosEntry("MSX.ROM",  "aa95aea2563cd5ec0a0919b44cc17d47", True,  "MSX BIOS"),
        BiosEntry("MSX2.ROM", "ec3a01c91f24fbddcbcab0ad301bc9ef", False, "MSX2 BIOS"),
        BiosEntry("MSX2EXT.ROM", "2183c2aff17cf4297bdb496de78c2e8a", False, "MSX2 SubROM"),
    ],
    "PC Engine CD": [
        BiosEntry("syscard3.pce", "ff1a674273fe3540ccef576376b7e26c", True, "PC Engine CD System Card 3.0"),
    ],
    "Philips CD-i": [
        BiosEntry("cdimono1.zip", "", True, "CD-i Mono-I BIOS"),
        BiosEntry("cdibios.zip",  "", False, "CD-i BIOS (alt)"),
    ],
    "3DO": [
        BiosEntry("panafz1.bin",  "f47264dd47fe30f73ab3c010015c155b", True,  "3DO Panasonic FZ-1 BIOS"),
        BiosEntry("panafz10.bin", "51f2f43ae2f3508a14d9f56597e2b3ce", False, "3DO Panasonic FZ-10 BIOS"),
        BiosEntry("goldstar.bin", "8639fd5e549571b7171e55774f8f29d0", False, "3DO GoldStar BIOS"),
    ],
    "Sega Master System": [
        BiosEntry("bios_E.sms", "840481177270d5642a14ca71ee72844c", False, "SMS BIOS (Europe)"),
        BiosEntry("bios_U.sms", "840481177270d5642a14ca71ee72844c", False, "SMS BIOS (USA)"),
        BiosEntry("bios_J.sms", "24a519c53f67b00640d0048ef7089105", False, "SMS BIOS (Japan)"),
    ],
    "Famicom Disk System": [
        BiosEntry("disksys.rom", "ca30b50f880eb660a320571e8afceb3f", True, "FDS BIOS"),
    ],
    "PC-FX": [
        BiosEntry("pcfx.rom", "08e36edbea28a017f79f8d4f7ff9b6d7", True, "PC-FX BIOS"),
    ],
    "Jaguar CD": [
        BiosEntry("jaguarcd.bin", "", False, "Jaguar CD BIOS"),
    ],
}


# ═══════════════════════════════════════════════════════════════════════
# Result dataclasses
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class BiosFileResult:
    """Result for a single BIOS file check."""
    filename: str
    system: str
    required: bool
    expected_md5: str
    actual_md5: str = ""
    found: bool = False
    found_path: str = ""
    valid: bool = False
    status: str = "missing"  # "valid", "bad_hash", "missing"
    desc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "system": self.system,
            "required": self.required,
            "expected_md5": self.expected_md5,
            "actual_md5": self.actual_md5,
            "found": self.found,
            "found_path": self.found_path,
            "valid": self.valid,
            "status": self.status,
            "desc": self.desc,
        }


@dataclass
class SystemBiosHealth:
    """Aggregated BIOS health for a single system."""
    system: str
    total_bios: int = 0
    required_bios: int = 0
    found: int = 0
    valid: int = 0
    bad_hash: int = 0
    missing_required: int = 0
    missing_optional: int = 0
    health_score: float = 0.0
    status: str = "unknown"  # "healthy", "degraded", "critical", "missing"
    files: list[BiosFileResult] = field(default_factory=list)
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "total_bios": self.total_bios,
            "required_bios": self.required_bios,
            "found": self.found,
            "valid": self.valid,
            "bad_hash": self.bad_hash,
            "missing_required": self.missing_required,
            "missing_optional": self.missing_optional,
            "health_score": self.health_score,
            "status": self.status,
            "files": [f.to_dict() for f in self.files],
            "issues": self.issues,
        }


@dataclass
class BiosAuditReport:
    """Full BIOS audit report across all systems."""
    scan_paths: list[str] = field(default_factory=list)
    total_systems: int = 0
    healthy_systems: int = 0
    degraded_systems: int = 0
    critical_systems: int = 0
    total_bios_checked: int = 0
    total_found: int = 0
    total_valid: int = 0
    total_bad_hash: int = 0
    total_missing_required: int = 0
    systems: list[SystemBiosHealth] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_paths": self.scan_paths,
            "total_systems": self.total_systems,
            "healthy_systems": self.healthy_systems,
            "degraded_systems": self.degraded_systems,
            "critical_systems": self.critical_systems,
            "total_bios_checked": self.total_bios_checked,
            "total_found": self.total_found,
            "total_valid": self.total_valid,
            "total_bad_hash": self.total_bad_hash,
            "total_missing_required": self.total_missing_required,
            "systems": [s.to_dict() for s in self.systems],
        }


# ═══════════════════════════════════════════════════════════════════════
# Hashing
# ═══════════════════════════════════════════════════════════════════════

def hash_file_md5(filepath: Path) -> str:
    """Compute MD5 of a file. Returns lowercase hex string (32 chars)."""
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)  # 1 MB chunks
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as exc:
        log.warning("MD5 failed for %s: %s", filepath, exc)
        return ""


# ═══════════════════════════════════════════════════════════════════════
# BIOS file search
# ═══════════════════════════════════════════════════════════════════════

def _find_bios_file(filename: str, search_paths: list[Path]) -> Optional[Path]:
    """Search for a BIOS file across multiple directories.

    Searches case-insensitively through all provided paths.
    Returns the first match found, or None.
    """
    target_lower = filename.lower()
    for search_dir in search_paths:
        if not search_dir.exists():
            continue
        # Direct match (case-insensitive on Windows, exact on Linux)
        direct = search_dir / filename
        if direct.exists():
            return direct
        # Case-insensitive fallback: scan directory
        try:
            for item in search_dir.iterdir():
                if item.is_file() and item.name.lower() == target_lower:
                    return item
        except (PermissionError, OSError):
            continue
    return None


def _build_search_paths(
    retroarch_system: str = "",
    emulators_root: str = "",
    extra_paths: Optional[list[str]] = None,
) -> list[Path]:
    """Build the list of directories to search for BIOS files.

    Priority order:
      1. RetroArch system directory
      2. Emulator-specific BIOS subdirectories
      3. Extra user-provided paths
    """
    paths: list[Path] = []

    # RetroArch system dir (highest priority)
    if retroarch_system:
        ra_sys = Path(retroarch_system)
        if ra_sys.exists():
            paths.append(ra_sys)
    else:
        # Try to auto-detect from config
        ra_cfg = cfg_get("paths.emulators_root", "")
        if ra_cfg:
            ra_base = Path(ra_cfg)
            # Common RetroArch locations
            for candidate in [
                ra_base / "RetroArch" / "system",
                ra_base / "retroarch" / "system",
                ra_base / "RetroArch-Win64" / "system",
            ]:
                if candidate.exists():
                    paths.append(candidate)

    # Emulators root — check for BIOS subdirs in each emulator folder
    if emulators_root:
        emu_root = Path(emulators_root)
    else:
        emu_root_cfg = cfg_get("paths.emulators_root", "")
        emu_root = Path(emu_root_cfg) if emu_root_cfg else None

    if emu_root and emu_root.exists():
        try:
            for emu_dir in emu_root.iterdir():
                if not emu_dir.is_dir():
                    continue
                # Check common BIOS subfolder names
                for bios_sub in ["bios", "BIOS", "system", "System", ""]:
                    candidate = emu_dir / bios_sub if bios_sub else emu_dir
                    if candidate.exists() and candidate.is_dir():
                        if candidate not in paths:
                            paths.append(candidate)
        except (PermissionError, OSError) as exc:
            log.warning("Cannot scan emulators root %s: %s", emu_root, exc)

    # Extra user-provided paths
    if extra_paths:
        for p in extra_paths:
            pp = Path(p)
            if pp.exists() and pp not in paths:
                paths.append(pp)

    return paths


# ═══════════════════════════════════════════════════════════════════════
# Verification
# ═══════════════════════════════════════════════════════════════════════

def verify_bios_file(entry: BiosEntry, search_paths: list[Path]) -> BiosFileResult:
    """Verify a single BIOS file against its expected checksum.

    Returns a BiosFileResult with status:
      - "valid":    file found and MD5 matches
      - "bad_hash": file found but MD5 differs
      - "missing":  file not found in any search path
    """
    result = BiosFileResult(
        filename=entry.filename,
        system=entry.system,
        required=entry.required,
        expected_md5=entry.md5,
        desc=entry.desc,
    )

    found_path = _find_bios_file(entry.filename, search_paths)

    if found_path is None:
        result.status = "missing"
        return result

    result.found = True
    result.found_path = str(found_path)

    # For archive-based BIOS (e.g. neogeo.zip), existence is sufficient
    if not entry.md5:
        result.valid = True
        result.status = "valid"
        log.debug("BIOS %s found (no hash to verify): %s", entry.filename, found_path)
        return result

    # Compute MD5 and compare
    actual_md5 = hash_file_md5(found_path)
    result.actual_md5 = actual_md5

    if actual_md5 == entry.md5:
        result.valid = True
        result.status = "valid"
        log.debug("BIOS %s verified OK: %s", entry.filename, found_path)
    else:
        result.status = "bad_hash"
        log.warning(
            "BIOS %s hash mismatch: expected %s, got %s (%s)",
            entry.filename, entry.md5, actual_md5, found_path,
        )

    return result


# ═══════════════════════════════════════════════════════════════════════
# System-level audit
# ═══════════════════════════════════════════════════════════════════════

def audit_system_bios(
    system: str,
    search_paths: list[Path],
    bios_entries: Optional[list[BiosEntry]] = None,
) -> SystemBiosHealth:
    """Audit BIOS health for a single system.

    Args:
        system: System name (must be a key in KNOWN_BIOS or entries provided).
        search_paths: Directories to search for BIOS files.
        bios_entries: Override BIOS entries (uses KNOWN_BIOS[system] if None).

    Returns:
        SystemBiosHealth with per-file results and aggregate scores.
    """
    entries = bios_entries or KNOWN_BIOS.get(system, [])
    health = SystemBiosHealth(system=system)
    health.total_bios = len(entries)
    health.required_bios = sum(1 for e in entries if e.required)

    for entry in entries:
        tagged = BiosEntry(
            filename=entry.filename,
            md5=entry.md5,
            required=entry.required,
            desc=entry.desc,
            system=system,
        )
        result = verify_bios_file(tagged, search_paths)
        health.files.append(result)

        if result.found:
            health.found += 1
        if result.valid:
            health.valid += 1
        if result.status == "bad_hash":
            health.bad_hash += 1
            health.issues.append({
                "severity": "warn",
                "msg": f"BIOS {result.filename} has wrong checksum "
                       f"(expected {result.expected_md5}, got {result.actual_md5})",
            })
        if result.status == "missing":
            if result.required:
                health.missing_required += 1
                health.issues.append({
                    "severity": "error",
                    "msg": f"Required BIOS missing: {result.filename} — {result.desc}",
                })
            else:
                health.missing_optional += 1
                health.issues.append({
                    "severity": "info",
                    "msg": f"Optional BIOS missing: {result.filename} — {result.desc}",
                })

    # Calculate health score
    health.health_score = _calc_health_score(health)
    health.status = _classify_health(health)

    return health


def _calc_health_score(health: SystemBiosHealth) -> float:
    """Calculate a 0-100 health score for a system's BIOS status.

    Scoring:
      - Required BIOS valid:  full weight (80% of score)
      - Optional BIOS valid:  partial weight (20% of score)
      - Bad hash:             half credit
    """
    if health.total_bios == 0:
        return 100.0

    req_weight = 0.8
    opt_weight = 0.2

    # Required score
    if health.required_bios > 0:
        req_valid = sum(
            1 for f in health.files
            if f.required and f.status == "valid"
        )
        req_bad = sum(
            1 for f in health.files
            if f.required and f.status == "bad_hash"
        )
        req_score = (req_valid + req_bad * 0.5) / health.required_bios
    else:
        req_score = 1.0

    # Optional score
    optional_count = health.total_bios - health.required_bios
    if optional_count > 0:
        opt_valid = sum(
            1 for f in health.files
            if not f.required and f.status == "valid"
        )
        opt_bad = sum(
            1 for f in health.files
            if not f.required and f.status == "bad_hash"
        )
        opt_score = (opt_valid + opt_bad * 0.5) / optional_count
    else:
        opt_score = 1.0

    return round((req_score * req_weight + opt_score * opt_weight) * 100, 1)


def _classify_health(health: SystemBiosHealth) -> str:
    """Classify system BIOS health status."""
    if health.missing_required > 0:
        return "critical"
    if health.bad_hash > 0:
        return "degraded"
    if health.health_score >= 80.0:
        return "healthy"
    if health.health_score >= 50.0:
        return "degraded"
    return "critical"


# ═══════════════════════════════════════════════════════════════════════
# Full audit
# ═══════════════════════════════════════════════════════════════════════

def audit_all_bios(
    retroarch_system: str = "",
    emulators_root: str = "",
    extra_paths: Optional[list[str]] = None,
    systems: Optional[list[str]] = None,
) -> BiosAuditReport:
    """Run a full BIOS audit across all known systems.

    Args:
        retroarch_system: Path to RetroArch system/ directory.
        emulators_root: Path to emulators root directory.
        extra_paths: Additional directories to search.
        systems: Limit audit to these systems (default: all known).

    Returns:
        BiosAuditReport with per-system results and aggregate totals.
    """
    search_paths = _build_search_paths(retroarch_system, emulators_root, extra_paths)
    report = BiosAuditReport(scan_paths=[str(p) for p in search_paths])

    target_systems = systems or list(KNOWN_BIOS.keys())
    log.info(
        "Starting BIOS audit: %d systems, %d search paths",
        len(target_systems), len(search_paths),
    )

    for system_name in target_systems:
        if system_name not in KNOWN_BIOS:
            log.warning("Unknown system: %s — skipping", system_name)
            continue
        sys_health = audit_system_bios(system_name, search_paths)
        report.systems.append(sys_health)

    # Aggregate totals
    report.total_systems = len(report.systems)
    for sh in report.systems:
        report.total_bios_checked += sh.total_bios
        report.total_found += sh.found
        report.total_valid += sh.valid
        report.total_bad_hash += sh.bad_hash
        report.total_missing_required += sh.missing_required

        if sh.status == "healthy":
            report.healthy_systems += 1
        elif sh.status == "degraded":
            report.degraded_systems += 1
        else:
            report.critical_systems += 1

    log.info(
        "BIOS audit complete: %d systems | %d/%d found | %d valid | %d bad hash | %d missing required",
        report.total_systems, report.total_found, report.total_bios_checked,
        report.total_valid, report.total_bad_hash, report.total_missing_required,
    )

    return report


# ═══════════════════════════════════════════════════════════════════════
# Custom BIOS database loading
# ═══════════════════════════════════════════════════════════════════════

def load_bios_dat(dat_path: Path) -> dict[str, list[BiosEntry]]:
    """Load a custom BIOS definition file.

    Supports simple TSV format:
      system<TAB>filename<TAB>md5<TAB>required<TAB>description

    Returns dict mapping system → list of BiosEntry.
    """
    entries: dict[str, list[BiosEntry]] = {}
    if not dat_path.exists():
        log.warning("BIOS DAT file not found: %s", dat_path)
        return entries

    try:
        with open(dat_path, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    log.warning("Skipping malformed line %d in %s", line_num, dat_path)
                    continue
                system = parts[0].strip()
                filename = parts[1].strip()
                md5 = parts[2].strip().lower()
                required = parts[3].strip().lower() in ("true", "1", "yes") if len(parts) > 3 else True
                desc = parts[4].strip() if len(parts) > 4 else ""

                entry = BiosEntry(filename=filename, md5=md5, required=required, desc=desc, system=system)
                entries.setdefault(system, []).append(entry)

        log.info("Loaded %d BIOS entries from %s", sum(len(v) for v in entries.values()), dat_path)
    except (OSError, UnicodeDecodeError) as exc:
        log.error("Failed to load BIOS DAT %s: %s", dat_path, exc)

    return entries


def merge_bios_database(custom_entries: dict[str, list[BiosEntry]]) -> None:
    """Merge custom BIOS entries into the global KNOWN_BIOS database.

    Custom entries for existing systems are appended.
    New systems are added.
    """
    for system, entries in custom_entries.items():
        if system in KNOWN_BIOS:
            existing_filenames = {e.filename.lower() for e in KNOWN_BIOS[system]}
            for entry in entries:
                if entry.filename.lower() not in existing_filenames:
                    KNOWN_BIOS[system].append(entry)
                    existing_filenames.add(entry.filename.lower())
        else:
            KNOWN_BIOS[system] = entries

    log.info("Merged custom BIOS database: %d systems total", len(KNOWN_BIOS))


# ═══════════════════════════════════════════════════════════════════════
# Utility functions
# ═══════════════════════════════════════════════════════════════════════

def list_known_systems() -> list[str]:
    """Return sorted list of all systems with known BIOS requirements."""
    return sorted(KNOWN_BIOS.keys())


def get_system_requirements(system: str) -> list[dict[str, Any]]:
    """Get BIOS requirements for a specific system."""
    entries = KNOWN_BIOS.get(system, [])
    return [e.to_dict() for e in entries]


def get_missing_bios_summary(report: BiosAuditReport) -> list[dict[str, str]]:
    """Extract a flat list of all missing required BIOS files from an audit report."""
    missing: list[dict[str, str]] = []
    for sys_health in report.systems:
        for file_result in sys_health.files:
            if file_result.status == "missing" and file_result.required:
                missing.append({
                    "system": file_result.system,
                    "filename": file_result.filename,
                    "expected_md5": file_result.expected_md5,
                    "desc": file_result.desc,
                })
    return missing
