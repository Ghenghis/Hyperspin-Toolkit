"""M56 — DAT File ROM Set Verification Engine.

Higher-level engine that manages multiple DAT files (No-Intro, Redump,
TOSEC) and provides:
  - DAT source identification and metadata parsing
  - Multi-system DAT index management
  - 1G1R (1 Game 1 ROM) set curation with configurable region priority
  - Region variant detection and filtering
  - Per-system completion reports
  - Integration with rom_audit.py for low-level parsing and hashing

Delegates to engines.rom_audit for DAT parsing and CRC/SHA1 verification.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

from engines.rom_audit import DATEntry, parse_dat_file, verify_roms

log = get_logger("dat_verifier")


# ═══════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════

# Default region priority for 1G1R curation (higher index = lower priority)
DEFAULT_REGION_PRIORITY: list[str] = [
    "USA",
    "World",
    "Europe",
    "Japan",
    "Brazil",
    "Korea",
    "China",
    "France",
    "Germany",
    "Spain",
    "Italy",
    "Australia",
    "Netherlands",
    "Sweden",
    "Canada",
    "Asia",
]

# Regex patterns for identifying regions in ROM names
REGION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("USA",         re.compile(r"\(USA\)",         re.IGNORECASE)),
    ("World",       re.compile(r"\(World\)",       re.IGNORECASE)),
    ("Europe",      re.compile(r"\(Europe\)",      re.IGNORECASE)),
    ("Japan",       re.compile(r"\(Japan\)",       re.IGNORECASE)),
    ("Brazil",      re.compile(r"\(Brazil\)",      re.IGNORECASE)),
    ("Korea",       re.compile(r"\(Korea\)",       re.IGNORECASE)),
    ("China",       re.compile(r"\(China\)",       re.IGNORECASE)),
    ("France",      re.compile(r"\(France\)",      re.IGNORECASE)),
    ("Germany",     re.compile(r"\(Germany\)",     re.IGNORECASE)),
    ("Spain",       re.compile(r"\(Spain\)",       re.IGNORECASE)),
    ("Italy",       re.compile(r"\(Italy\)",       re.IGNORECASE)),
    ("Australia",   re.compile(r"\(Australia\)",   re.IGNORECASE)),
    ("Netherlands", re.compile(r"\(Netherlands\)", re.IGNORECASE)),
    ("Sweden",      re.compile(r"\(Sweden\)",      re.IGNORECASE)),
    ("Canada",      re.compile(r"\(Canada\)",      re.IGNORECASE)),
    ("Asia",        re.compile(r"\(Asia\)",        re.IGNORECASE)),
]

# Patterns for identifying DAT source
DAT_SOURCE_PATTERNS: dict[str, list[str]] = {
    "No-Intro":  ["no-intro", "nointro"],
    "Redump":    ["redump"],
    "TOSEC":     ["tosec"],
    "MAME":      ["mame"],
    "FBNeo":     ["fbneo", "fbalpha"],
}

# Tags that indicate non-game entries (demos, betas, protos, etc.)
NONGAME_TAGS: list[re.Pattern] = [
    re.compile(r"\(Proto\)",       re.IGNORECASE),
    re.compile(r"\(Beta\)",        re.IGNORECASE),
    re.compile(r"\(Demo\)",        re.IGNORECASE),
    re.compile(r"\(Sample\)",      re.IGNORECASE),
    re.compile(r"\(Unl\)",         re.IGNORECASE),
    re.compile(r"\(Pirate\)",      re.IGNORECASE),
    re.compile(r"\[BIOS\]",        re.IGNORECASE),
    re.compile(r"\(Program\)",     re.IGNORECASE),
    re.compile(r"\(Test Program\)",re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class DATMetadata:
    """Metadata extracted from a DAT file header."""
    name: str = ""
    description: str = ""
    version: str = ""
    author: str = ""
    homepage: str = ""
    source: str = ""  # "No-Intro", "Redump", "TOSEC", "MAME", "Unknown"
    system: str = ""
    total_games: int = 0
    total_roms: int = 0
    filepath: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "homepage": self.homepage,
            "source": self.source,
            "system": self.system,
            "total_games": self.total_games,
            "total_roms": self.total_roms,
            "filepath": self.filepath,
        }


@dataclass
class OneG1REntry:
    """A curated 1G1R entry — best region variant of a game."""
    base_name: str
    selected_game: str
    region: str
    crc32: str = ""
    all_variants: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_name": self.base_name,
            "selected_game": self.selected_game,
            "region": self.region,
            "crc32": self.crc32,
            "all_variants": self.all_variants,
        }


@dataclass
class SystemCompletion:
    """Completion report for a single system."""
    system: str
    dat_source: str = ""
    dat_version: str = ""
    total_in_dat: int = 0
    total_on_disk: int = 0
    verified: int = 0
    bad_hash: int = 0
    missing: int = 0
    extra: int = 0
    completeness_pct: float = 0.0
    oneg1r_total: int = 0
    oneg1r_have: int = 0
    oneg1r_pct: float = 0.0
    missing_games: list[str] = field(default_factory=list)
    extra_games: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "dat_source": self.dat_source,
            "dat_version": self.dat_version,
            "total_in_dat": self.total_in_dat,
            "total_on_disk": self.total_on_disk,
            "verified": self.verified,
            "bad_hash": self.bad_hash,
            "missing": self.missing,
            "extra": self.extra,
            "completeness_pct": self.completeness_pct,
            "oneg1r_total": self.oneg1r_total,
            "oneg1r_have": self.oneg1r_have,
            "oneg1r_pct": self.oneg1r_pct,
            "missing_games": self.missing_games[:100],  # cap for output size
            "extra_games": self.extra_games[:100],
        }


@dataclass
class DATVerificationReport:
    """Full DAT verification report across multiple systems."""
    systems_checked: int = 0
    total_verified: int = 0
    total_bad_hash: int = 0
    total_missing: int = 0
    total_extra: int = 0
    overall_completeness_pct: float = 0.0
    systems: list[SystemCompletion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "systems_checked": self.systems_checked,
            "total_verified": self.total_verified,
            "total_bad_hash": self.total_bad_hash,
            "total_missing": self.total_missing,
            "total_extra": self.total_extra,
            "overall_completeness_pct": self.overall_completeness_pct,
            "systems": [s.to_dict() for s in self.systems],
        }


# ═══════════════════════════════════════════════════════════════════════
# DAT metadata parsing
# ═══════════════════════════════════════════════════════════════════════

def identify_dat_source(filepath: Path, content: str = "") -> str:
    """Identify the source of a DAT file (No-Intro, Redump, TOSEC, etc.).

    Checks filename first, then DAT header content.
    """
    name_lower = filepath.name.lower()
    check_text = name_lower + " " + content[:2000].lower()

    for source, keywords in DAT_SOURCE_PATTERNS.items():
        for kw in keywords:
            if kw in check_text:
                return source
    return "Unknown"


def parse_dat_metadata(dat_path: Path) -> DATMetadata:
    """Extract metadata from a DAT file header.

    Handles both XML and CLRMamePro text format headers.
    """
    dat_path = Path(dat_path)
    meta = DATMetadata(filepath=str(dat_path))

    if not dat_path.exists():
        log.warning("DAT file not found: %s", dat_path)
        return meta

    try:
        content = dat_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.error("Cannot read DAT %s: %s", dat_path, exc)
        return meta

    meta.source = identify_dat_source(dat_path, content)

    # Try XML header
    if content.lstrip().startswith("<?xml") or content.lstrip().startswith("<"):
        meta = _parse_xml_header(dat_path, content, meta)
    else:
        meta = _parse_clrmamepro_header(content, meta)

    # Count entries via rom_audit parser
    entries = parse_dat_file(dat_path)
    game_names = {e.game_name for e in entries}
    meta.total_games = len(game_names)
    meta.total_roms = len(entries)

    # Infer system from DAT name if not set
    if not meta.system:
        meta.system = _infer_system_from_filename(dat_path)

    return meta


def _parse_xml_header(dat_path: Path, content: str, meta: DATMetadata) -> DATMetadata:
    """Extract header info from XML DAT."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return meta

    # Logiqx: <datafile><header>...</header>
    header = root.find("header")
    if header is not None:
        meta.name = (header.findtext("name") or "").strip()
        meta.description = (header.findtext("description") or "").strip()
        meta.version = (header.findtext("version") or "").strip()
        meta.author = (header.findtext("author") or "").strip()
        meta.homepage = (header.findtext("homepage") or "").strip()

    # MAME: <mame build="0.260">
    if root.tag == "mame":
        meta.name = meta.name or "MAME"
        meta.version = root.get("build", meta.version)
        meta.source = "MAME"

    return meta


def _parse_clrmamepro_header(content: str, meta: DATMetadata) -> DATMetadata:
    """Extract header info from CLRMamePro text format."""
    header_match = re.search(
        r'clrmamepro\s*\((.*?)\)', content[:3000], re.DOTALL | re.IGNORECASE
    )
    if header_match:
        block = header_match.group(1)
        for field_name, attr in [
            ("name", "name"),
            ("description", "description"),
            ("version", "version"),
            ("author", "author"),
            ("homepage", "homepage"),
        ]:
            m = re.search(rf'{field_name}\s+"([^"]*)"', block, re.IGNORECASE)
            if m:
                setattr(meta, attr, m.group(1).strip())
    return meta


def _infer_system_from_filename(dat_path: Path) -> str:
    """Infer system name from DAT filename by stripping source prefixes."""
    stem = dat_path.stem
    # Strip common prefixes
    for prefix in ["No-Intro - ", "Redump - ", "TOSEC - ", "TOSEC ("]:
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    # Strip version suffixes like " (20231201-123456)"
    stem = re.sub(r'\s*\(\d{8}[^)]*\)\s*$', '', stem)
    return stem.strip()


# ═══════════════════════════════════════════════════════════════════════
# Region detection and 1G1R curation
# ═══════════════════════════════════════════════════════════════════════

def detect_regions(game_name: str) -> list[str]:
    """Detect all regions in a game name (e.g., "(USA, Europe)" → ["USA", "Europe"])."""
    regions: list[str] = []
    for region, pattern in REGION_PATTERNS:
        if pattern.search(game_name):
            regions.append(region)

    # Also check for multi-region tags like "(USA, Europe)"
    multi_match = re.search(r'\(([^)]+)\)', game_name)
    if multi_match:
        inner = multi_match.group(1)
        for part in inner.split(","):
            part = part.strip()
            for region, _ in REGION_PATTERNS:
                if part.lower() == region.lower() and region not in regions:
                    regions.append(region)

    return regions


def is_nongame(game_name: str) -> bool:
    """Check if a game name represents a non-game entry (BIOS, demo, proto, etc.)."""
    for pattern in NONGAME_TAGS:
        if pattern.search(game_name):
            return True
    return False


def extract_base_name(game_name: str) -> str:
    """Extract the base game name by stripping region and variant tags.

    Example:
        "Super Mario Bros. (USA) (Rev 1)" → "Super Mario Bros."
        "Sonic the Hedgehog (Japan, Europe)" → "Sonic the Hedgehog"
    """
    # Strip everything in parentheses and brackets
    base = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', game_name).strip()
    return base


def curate_1g1r(
    dat_entries: list[DATEntry],
    region_priority: Optional[list[str]] = None,
    exclude_nongame: bool = True,
) -> list[OneG1REntry]:
    """Curate a 1G1R (1 Game 1 ROM) set from DAT entries.

    For each unique game, selects the best region variant based on priority.

    Args:
        dat_entries: Parsed DAT entries.
        region_priority: Region preference order (default: USA first).
        exclude_nongame: Skip BIOS, demos, protos, etc.

    Returns:
        List of OneG1REntry, one per unique game.
    """
    priority = region_priority or DEFAULT_REGION_PRIORITY

    # Group entries by base name
    groups: dict[str, list[DATEntry]] = defaultdict(list)
    for entry in dat_entries:
        if exclude_nongame and is_nongame(entry.game_name):
            continue
        base = extract_base_name(entry.game_name)
        if base:
            groups[base].append(entry)

    results: list[OneG1REntry] = []
    for base_name, variants in sorted(groups.items()):
        # Deduplicate by game_name
        seen: set[str] = set()
        unique_variants: list[DATEntry] = []
        for v in variants:
            if v.game_name not in seen:
                seen.add(v.game_name)
                unique_variants.append(v)

        # Score each variant by region priority
        best: Optional[DATEntry] = None
        best_score = len(priority) + 1  # worse than any match
        best_region = ""

        for variant in unique_variants:
            regions = detect_regions(variant.game_name)
            variant_score = len(priority) + 1
            variant_region = regions[0] if regions else "Unknown"

            for region in regions:
                try:
                    idx = priority.index(region)
                    if idx < variant_score:
                        variant_score = idx
                        variant_region = region
                except ValueError:
                    pass

            if variant_score < best_score:
                best_score = variant_score
                best = variant
                best_region = variant_region

        if best is None and unique_variants:
            best = unique_variants[0]
            best_region = "Unknown"

        if best:
            results.append(OneG1REntry(
                base_name=base_name,
                selected_game=best.game_name,
                region=best_region,
                crc32=best.crc32,
                all_variants=[v.game_name for v in unique_variants],
            ))

    log.info("1G1R curation: %d unique games from %d entries", len(results), len(dat_entries))
    return results


# ═══════════════════════════════════════════════════════════════════════
# System verification with completion tracking
# ═══════════════════════════════════════════════════════════════════════

def verify_system(
    system: str,
    rom_dir: str | Path,
    dat_path: str | Path,
    *,
    use_sha1: bool = False,
    compute_1g1r: bool = True,
    region_priority: Optional[list[str]] = None,
) -> SystemCompletion:
    """Verify a system's ROM set against its DAT and compute completion.

    Args:
        system: System name.
        rom_dir: Directory containing ROM files.
        dat_path: Path to the DAT file.
        use_sha1: Also verify SHA1 hashes.
        compute_1g1r: Also compute 1G1R completion.
        region_priority: Custom region priority for 1G1R.

    Returns:
        SystemCompletion with full verification results.
    """
    rom_dir = Path(rom_dir)
    dat_path = Path(dat_path)

    comp = SystemCompletion(system=system)

    # Get DAT metadata
    meta = parse_dat_metadata(dat_path)
    comp.dat_source = meta.source
    comp.dat_version = meta.version

    # Run verification via rom_audit
    result = verify_roms(
        rom_dir, dat_path,
        use_sha1=use_sha1,
        system_name=system,
    )

    comp.total_in_dat = result.get("total_in_dat", 0)
    comp.verified = result.get("verified", 0)
    comp.bad_hash = result.get("bad_hash", 0)
    comp.missing = result.get("missing", 0)
    comp.extra = result.get("extra", 0)
    comp.completeness_pct = result.get("completeness_pct", 0.0)

    # Count ROMs on disk
    if rom_dir.exists():
        comp.total_on_disk = sum(1 for f in rom_dir.iterdir() if f.is_file())

    # Extract missing and extra game names
    for r in result.get("results", []):
        if r.get("status") == "missing" and r.get("game_name"):
            if r["game_name"] not in comp.missing_games:
                comp.missing_games.append(r["game_name"])
        elif r.get("status") == "extra" and r.get("game_name"):
            if r["game_name"] not in comp.extra_games:
                comp.extra_games.append(r["game_name"])

    # 1G1R computation
    if compute_1g1r:
        dat_entries = parse_dat_file(dat_path)
        oneg1r_set = curate_1g1r(dat_entries, region_priority)
        comp.oneg1r_total = len(oneg1r_set)

        # Check which 1G1R games we have on disk
        disk_stems = set()
        if rom_dir.exists():
            disk_stems = {f.stem.lower() for f in rom_dir.iterdir() if f.is_file()}

        have_count = 0
        for entry in oneg1r_set:
            # Check if the selected variant is on disk
            if entry.selected_game.lower() in disk_stems:
                have_count += 1
            # Also check base name
            elif entry.base_name.lower() in disk_stems:
                have_count += 1
        comp.oneg1r_have = have_count
        comp.oneg1r_pct = round(
            have_count / comp.oneg1r_total * 100, 1
        ) if comp.oneg1r_total > 0 else 0.0

    log.info(
        "System %s: %d/%d verified (%.1f%%), 1G1R: %d/%d (%.1f%%)",
        system, comp.verified, comp.total_in_dat, comp.completeness_pct,
        comp.oneg1r_have, comp.oneg1r_total, comp.oneg1r_pct,
    )

    return comp


# ═══════════════════════════════════════════════════════════════════════
# Multi-system batch verification
# ═══════════════════════════════════════════════════════════════════════

def verify_all_systems(
    dat_dir: Optional[str | Path] = None,
    roms_root: Optional[str | Path] = None,
    *,
    use_sha1: bool = False,
    compute_1g1r: bool = True,
    region_priority: Optional[list[str]] = None,
    systems: Optional[list[str]] = None,
) -> DATVerificationReport:
    """Verify all systems that have both ROM directories and DAT files.

    Args:
        dat_dir: Directory containing DAT files.
        roms_root: Root directory containing per-system ROM subdirectories.
        use_sha1: Also verify SHA1 hashes.
        compute_1g1r: Compute 1G1R completion per system.
        region_priority: Custom region priority for 1G1R.
        systems: Limit to these systems (default: auto-discover).

    Returns:
        DATVerificationReport with per-system completion data.
    """
    hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    if dat_dir is None:
        dat_dir = Path(cfg_get("paths.dat_root", str(hs_root / "DATs")))
    else:
        dat_dir = Path(dat_dir)

    if roms_root is None:
        roms_root = Path(cfg_get("paths.roms_root", str(hs_root / "ROMs")))
    else:
        roms_root = Path(roms_root)

    report = DATVerificationReport()

    if not dat_dir.exists():
        log.warning("DAT directory not found: %s", dat_dir)
        return report

    # Discover DAT files
    dat_files: list[Path] = []
    for ext in ("*.dat", "*.xml"):
        dat_files.extend(sorted(dat_dir.glob(ext)))

    log.info("DAT verification: %d DAT files found in %s", len(dat_files), dat_dir)

    for dat_file in dat_files:
        system_name = dat_file.stem

        # Filter to requested systems
        if systems and system_name not in systems:
            continue

        # Find ROM directory
        rom_dir = _find_rom_dir(system_name, roms_root, hs_root)
        if rom_dir is None:
            log.debug("No ROM directory for %s — skipping", system_name)
            continue

        comp = verify_system(
            system_name, rom_dir, dat_file,
            use_sha1=use_sha1,
            compute_1g1r=compute_1g1r,
            region_priority=region_priority,
        )
        report.systems.append(comp)

    # Aggregate
    report.systems_checked = len(report.systems)
    total_in_dat = 0
    total_verified = 0
    for s in report.systems:
        report.total_verified += s.verified
        report.total_bad_hash += s.bad_hash
        report.total_missing += s.missing
        report.total_extra += s.extra
        total_in_dat += s.total_in_dat
        total_verified += s.verified

    report.overall_completeness_pct = round(
        total_verified / total_in_dat * 100, 1
    ) if total_in_dat > 0 else 0.0

    log.info(
        "DAT verification complete: %d systems, %.1f%% overall completeness",
        report.systems_checked, report.overall_completeness_pct,
    )

    return report


def _find_rom_dir(system: str, roms_root: Path, hs_root: Path) -> Optional[Path]:
    """Find the ROM directory for a system across common locations."""
    candidates = [
        roms_root / system,
        roms_root / system / "roms",
        hs_root / system,
        hs_root / "ROMs" / system,
    ]
    for c in candidates:
        if c.exists() and c.is_dir():
            return c
    return None


# ═══════════════════════════════════════════════════════════════════════
# DAT index management
# ═══════════════════════════════════════════════════════════════════════

def index_dat_directory(dat_dir: str | Path) -> list[DATMetadata]:
    """Scan a directory and index all DAT files with metadata.

    Returns sorted list of DATMetadata for each DAT file found.
    """
    dat_dir = Path(dat_dir)
    if not dat_dir.exists():
        log.warning("DAT directory not found: %s", dat_dir)
        return []

    index: list[DATMetadata] = []
    for ext in ("*.dat", "*.xml"):
        for dat_file in sorted(dat_dir.glob(ext)):
            meta = parse_dat_metadata(dat_file)
            index.append(meta)

    log.info("Indexed %d DAT files from %s", len(index), dat_dir)
    return index


def get_dat_summary(dat_dir: str | Path) -> dict[str, Any]:
    """Get a summary of all DAT files organized by source."""
    index = index_dat_directory(dat_dir)
    by_source: dict[str, list[dict]] = defaultdict(list)
    for meta in index:
        by_source[meta.source].append(meta.to_dict())

    return {
        "total_dat_files": len(index),
        "total_games": sum(m.total_games for m in index),
        "total_roms": sum(m.total_roms for m in index),
        "by_source": dict(by_source),
    }
