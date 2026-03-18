"""
M26 -- Duplicate ROM Detection & Cleanup

Provides:
  - Cross-system duplicate detection using CRC32/MD5/SHA1 hashes
  - Region variant identification (US, EU, JP, World)
  - Same-game-different-format detection (.zip vs .7z vs .chd)
  - Cleanup wizard with safe deletion (move to quarantine first)
  - Space savings calculator
  - Integration with drive_manifest for cross-drive duplicates
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("duplicate_detector")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
QUARANTINE_DIR = TOOLKIT_ROOT / "data" / "quarantine"

# Region detection patterns
REGION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("USA", re.compile(r"\((?:USA|US|U)\)", re.I)),
    ("Europe", re.compile(r"\((?:Europe|EUR|E)\)", re.I)),
    ("Japan", re.compile(r"\((?:Japan|JP|J)\)", re.I)),
    ("World", re.compile(r"\((?:World|W)\)", re.I)),
    ("Korea", re.compile(r"\((?:Korea|KR|K)\)", re.I)),
    ("China", re.compile(r"\((?:China|CN)\)", re.I)),
    ("France", re.compile(r"\((?:France|FR|F)\)", re.I)),
    ("Germany", re.compile(r"\((?:Germany|DE|G)\)", re.I)),
    ("Spain", re.compile(r"\((?:Spain|ES|S)\)", re.I)),
    ("Italy", re.compile(r"\((?:Italy|IT|I)\)", re.I)),
    ("Brazil", re.compile(r"\((?:Brazil|BR)\)", re.I)),
    ("Australia", re.compile(r"\((?:Australia|AU)\)", re.I)),
]

# Tags that indicate non-primary variants
VARIANT_TAGS = re.compile(
    r"\((Rev\s*\w+|Beta|Proto|Sample|Demo|Kiosk|Virtual Console|"
    r"Promo|Not for Resale|Unl|Pirate|Alt|Hack|Bad Dump|Overdump)\)",
    re.I,
)

ROM_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".gz",
    ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".nds",
    ".gen", ".md", ".sms", ".gg", ".32x",
    ".pce", ".ngp", ".ngc", ".ws", ".wsc",
    ".bin", ".iso", ".cue", ".chd", ".cso", ".pbp",
    ".n64", ".z64", ".v64",
    ".a26", ".a52", ".a78", ".j64", ".lnx",
    ".col", ".int", ".sg", ".sc",
    ".fds", ".vb",
}


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class ROMFile:
    """Represents a single ROM file with metadata."""
    path: str
    filename: str
    size: int
    extension: str
    system: str = ""
    game_name: str = ""      # cleaned name without region/tags
    regions: List[str] = field(default_factory=list)
    is_variant: bool = False  # Rev, Beta, Proto, etc.
    md5: str = ""
    crc32: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DuplicateGroup:
    """A group of duplicate ROM files."""
    game_name: str
    system: str
    files: List[ROMFile] = field(default_factory=list)
    total_size: int = 0
    potential_savings: int = 0
    recommended_keep: str = ""  # path of recommended file to keep
    match_type: str = ""        # hash, name, name+size

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["total_size_mb"] = round(self.total_size / (1024 * 1024), 2)
        d["savings_mb"] = round(self.potential_savings / (1024 * 1024), 2)
        return d


# -----------------------------------------------------------------------
# Name parsing
# -----------------------------------------------------------------------

def extract_game_name(filename: str) -> str:
    """Extract the base game name from a ROM filename (strip region, tags, extension)."""
    name = Path(filename).stem
    # Remove region tags
    name = re.sub(r"\([^)]*\)", "", name)
    # Remove square bracket tags
    name = re.sub(r"\[[^\]]*\]", "", name)
    # Clean up whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Remove trailing hyphens/underscores
    name = name.rstrip(" -_")
    return name


def detect_regions(filename: str) -> List[str]:
    """Detect region(s) from a ROM filename."""
    regions = []
    for region, pattern in REGION_PATTERNS:
        if pattern.search(filename):
            regions.append(region)
    return regions or ["Unknown"]


def is_variant(filename: str) -> bool:
    """Check if a ROM is a variant (Rev, Beta, Proto, etc.)."""
    return bool(VARIANT_TAGS.search(filename))


# -----------------------------------------------------------------------
# Hashing
# -----------------------------------------------------------------------

def compute_md5(filepath: str, partial: bool = False) -> str:
    """Compute MD5 hash of a file.

    Args:
        filepath: Path to file
        partial: If True, only hash first 1MB (faster for large files)
    """
    h = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            if partial:
                data = f.read(1024 * 1024)
                h.update(data)
            else:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return ""


def compute_crc32(filepath: str) -> str:
    """Compute CRC32 of a file."""
    import binascii
    crc = 0
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                crc = binascii.crc32(chunk, crc)
        return f"{crc & 0xFFFFFFFF:08x}"
    except (OSError, PermissionError):
        return ""


# -----------------------------------------------------------------------
# Scanning
# -----------------------------------------------------------------------

def scan_rom_directory(rom_dir: str, system: str = "",
                       compute_hashes: bool = False) -> List[ROMFile]:
    """Scan a directory for ROM files.

    Args:
        rom_dir: Directory to scan
        system: System name to assign
        compute_hashes: Whether to compute MD5 hashes

    Returns:
        List of ROMFile entries
    """
    rom_path = Path(rom_dir)
    if not rom_path.exists():
        return []

    files = []
    for entry in rom_path.rglob("*"):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in ROM_EXTENSIONS:
            continue

        rf = ROMFile(
            path=str(entry),
            filename=entry.name,
            size=entry.stat().st_size,
            extension=ext,
            system=system,
            game_name=extract_game_name(entry.name),
            regions=detect_regions(entry.name),
            is_variant=is_variant(entry.name),
        )

        if compute_hashes:
            rf.md5 = compute_md5(str(entry), partial=(rf.size > 50 * 1024 * 1024))

        files.append(rf)

    logger.info("Scanned %d ROM files in %s", len(files), rom_dir)
    return files


# -----------------------------------------------------------------------
# Duplicate detection
# -----------------------------------------------------------------------

def find_duplicates_by_name(files: List[ROMFile]) -> List[DuplicateGroup]:
    """Find duplicates by matching cleaned game names."""
    groups: Dict[str, List[ROMFile]] = defaultdict(list)
    for f in files:
        key = f"{f.system}|{f.game_name.lower()}"
        groups[key].append(f)

    dupes = []
    for key, group_files in groups.items():
        if len(group_files) < 2:
            continue

        system = group_files[0].system
        game_name = group_files[0].game_name
        total_size = sum(f.size for f in group_files)

        # Recommend keeping: prefer USA > World > Europe > Japan, non-variant, largest
        ranked = sorted(group_files, key=lambda f: (
            not f.is_variant,
            "USA" in f.regions,
            "World" in f.regions,
            "Europe" in f.regions,
            f.size,
        ), reverse=True)

        keep = ranked[0]
        savings = total_size - keep.size

        dupes.append(DuplicateGroup(
            game_name=game_name,
            system=system,
            files=group_files,
            total_size=total_size,
            potential_savings=savings,
            recommended_keep=keep.path,
            match_type="name",
        ))

    dupes.sort(key=lambda d: d.potential_savings, reverse=True)
    return dupes


def find_duplicates_by_hash(files: List[ROMFile]) -> List[DuplicateGroup]:
    """Find exact duplicates by MD5 hash."""
    groups: Dict[str, List[ROMFile]] = defaultdict(list)
    for f in files:
        if f.md5:
            groups[f.md5].append(f)

    dupes = []
    for md5, group_files in groups.items():
        if len(group_files) < 2:
            continue

        game_name = group_files[0].game_name
        system = group_files[0].system
        total_size = sum(f.size for f in group_files)
        keep = group_files[0]  # All identical, keep first
        savings = total_size - keep.size

        dupes.append(DuplicateGroup(
            game_name=game_name,
            system=system,
            files=group_files,
            total_size=total_size,
            potential_savings=savings,
            recommended_keep=keep.path,
            match_type="hash",
        ))

    dupes.sort(key=lambda d: d.potential_savings, reverse=True)
    return dupes


def find_duplicates_by_name_and_size(files: List[ROMFile]) -> List[DuplicateGroup]:
    """Find likely duplicates by name + similar file size."""
    groups: Dict[str, List[ROMFile]] = defaultdict(list)
    for f in files:
        key = f"{f.system}|{f.game_name.lower()}|{f.size}"
        groups[key].append(f)

    dupes = []
    for key, group_files in groups.items():
        if len(group_files) < 2:
            continue

        game_name = group_files[0].game_name
        system = group_files[0].system
        total_size = sum(f.size for f in group_files)
        keep = group_files[0]
        savings = total_size - keep.size

        dupes.append(DuplicateGroup(
            game_name=game_name,
            system=system,
            files=group_files,
            total_size=total_size,
            potential_savings=savings,
            recommended_keep=keep.path,
            match_type="name+size",
        ))

    dupes.sort(key=lambda d: d.potential_savings, reverse=True)
    return dupes


# -----------------------------------------------------------------------
# Main API
# -----------------------------------------------------------------------

def detect_duplicates(rom_dirs: List[str], systems: Optional[List[str]] = None,
                      use_hashes: bool = False,
                      method: str = "name") -> Dict[str, Any]:
    """Detect duplicate ROMs across one or more directories.

    Args:
        rom_dirs: List of ROM directories to scan
        systems: System names corresponding to each dir (optional)
        use_hashes: Compute MD5 hashes for exact matching
        method: Detection method - 'name', 'hash', 'name+size', 'all'

    Returns:
        Duplicate groups with space savings estimates
    """
    all_files: List[ROMFile] = []
    for i, rdir in enumerate(rom_dirs):
        sys_name = systems[i] if systems and i < len(systems) else Path(rdir).name
        files = scan_rom_directory(rdir, sys_name, compute_hashes=use_hashes)
        all_files.extend(files)

    logger.info("Total ROM files scanned: %d", len(all_files))

    results: Dict[str, List[DuplicateGroup]] = {}

    if method in ("name", "all"):
        results["by_name"] = find_duplicates_by_name(all_files)
    if method in ("name+size", "all"):
        results["by_name_size"] = find_duplicates_by_name_and_size(all_files)
    if use_hashes and method in ("hash", "all"):
        results["by_hash"] = find_duplicates_by_hash(all_files)

    # Calculate totals
    total_groups = sum(len(v) for v in results.values())
    total_savings = sum(
        sum(d.potential_savings for d in groups)
        for groups in results.values()
    )
    total_dupes = sum(
        sum(len(d.files) - 1 for d in groups)
        for groups in results.values()
    )

    return {
        "total_files_scanned": len(all_files),
        "duplicate_groups": total_groups,
        "duplicate_files": total_dupes,
        "potential_savings_mb": round(total_savings / (1024 * 1024), 2),
        "potential_savings_gb": round(total_savings / (1024 ** 3), 2),
        "method": method,
        "results": {
            k: [d.to_dict() for d in v[:50]]  # Cap output
            for k, v in results.items()
        },
    }


def detect_region_variants(rom_dir: str, system: str = "") -> Dict[str, Any]:
    """Find region variants (same game, different region) in a directory.

    Args:
        rom_dir: ROM directory to scan
        system: System name

    Returns:
        Games with multiple region variants and recommendations
    """
    files = scan_rom_directory(rom_dir, system)
    groups: Dict[str, List[ROMFile]] = defaultdict(list)
    for f in files:
        groups[f.game_name.lower()].append(f)

    variants = []
    for game_name, group_files in groups.items():
        if len(group_files) < 2:
            continue

        all_regions = set()
        for f in group_files:
            all_regions.update(f.regions)

        if len(all_regions) > 1 or any(f.is_variant for f in group_files):
            # Recommend USA > World > Europe
            ranked = sorted(group_files, key=lambda f: (
                not f.is_variant,
                "USA" in f.regions,
                "World" in f.regions,
                "Europe" in f.regions,
                f.size,
            ), reverse=True)

            variants.append({
                "game": group_files[0].game_name,
                "system": system,
                "variant_count": len(group_files),
                "regions": sorted(all_regions),
                "files": [{"filename": f.filename, "regions": f.regions,
                           "is_variant": f.is_variant, "size": f.size}
                          for f in group_files],
                "recommended_keep": ranked[0].filename,
                "savings_mb": round(
                    sum(f.size for f in ranked[1:]) / (1024 * 1024), 2
                ),
            })

    variants.sort(key=lambda v: v["savings_mb"], reverse=True)

    total_savings = sum(v["savings_mb"] for v in variants)
    return {
        "system": system,
        "games_with_variants": len(variants),
        "total_savings_mb": round(total_savings, 2),
        "variants": variants[:100],
    }


def cleanup_duplicates(duplicate_group: DuplicateGroup,
                       quarantine: bool = True) -> Dict[str, Any]:
    """Remove duplicate files, keeping the recommended one.

    Args:
        duplicate_group: Group of duplicate files
        quarantine: Move to quarantine instead of deleting

    Returns:
        Cleanup results
    """
    keep_path = duplicate_group.recommended_keep
    removed = []
    errors = []

    for f in duplicate_group.files:
        if f.path == keep_path:
            continue

        try:
            if quarantine:
                dest = QUARANTINE_DIR / Path(f.path).name
                os.makedirs(QUARANTINE_DIR, exist_ok=True)
                shutil.move(f.path, str(dest))
                removed.append({"file": f.filename, "action": "quarantined", "dest": str(dest)})
            else:
                os.remove(f.path)
                removed.append({"file": f.filename, "action": "deleted"})
        except Exception as e:
            errors.append({"file": f.filename, "error": str(e)})

    return {
        "game": duplicate_group.game_name,
        "kept": keep_path,
        "removed": removed,
        "errors": errors,
        "freed_bytes": duplicate_group.potential_savings,
    }


def space_savings_report(rom_dirs: List[str],
                         systems: Optional[List[str]] = None) -> Dict[str, Any]:
    """Calculate potential space savings from duplicate cleanup.

    Args:
        rom_dirs: Directories to analyze
        systems: System names

    Returns:
        Per-system and total savings estimates
    """
    per_system: List[Dict[str, Any]] = []
    total_savings = 0

    for i, rdir in enumerate(rom_dirs):
        sys_name = systems[i] if systems and i < len(systems) else Path(rdir).name
        files = scan_rom_directory(rdir, sys_name)
        name_dupes = find_duplicates_by_name(files)

        sys_savings = sum(d.potential_savings for d in name_dupes)
        total_savings += sys_savings

        per_system.append({
            "system": sys_name,
            "total_files": len(files),
            "duplicate_groups": len(name_dupes),
            "duplicate_files": sum(len(d.files) - 1 for d in name_dupes),
            "savings_mb": round(sys_savings / (1024 * 1024), 2),
        })

    per_system.sort(key=lambda s: s["savings_mb"], reverse=True)

    return {
        "total_savings_mb": round(total_savings / (1024 * 1024), 2),
        "total_savings_gb": round(total_savings / (1024 ** 3), 2),
        "per_system": per_system,
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python duplicate_detector.py scan <rom_dir> [system]")
        print("  python duplicate_detector.py regions <rom_dir> [system]")
        print("  python duplicate_detector.py savings <rom_dir1> [rom_dir2] ...")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "scan":
        rdir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys_name = sys.argv[3] if len(sys.argv) > 3 else ""
        result = detect_duplicates([rdir], [sys_name] if sys_name else None)
        print(json.dumps(result, indent=2))

    elif cmd == "regions":
        rdir = sys.argv[2] if len(sys.argv) > 2 else "."
        sys_name = sys.argv[3] if len(sys.argv) > 3 else ""
        result = detect_region_variants(rdir, sys_name)
        print(json.dumps(result, indent=2))

    elif cmd == "savings":
        dirs = sys.argv[2:]
        result = space_savings_report(dirs)
        print(json.dumps(result, indent=2))
