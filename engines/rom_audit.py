"""ROM Audit Engine — CRC32/SHA1 verification against DAT files.

Milestone M6: Verify ROM integrity by comparing actual file hashes against
known-good values from DAT files (CLRMamePro / MAME XML format).

Supports:
  - CLRMamePro .dat format (text-based)
  - MAME -listxml style XML
  - HyperSpin XML databases (name-only matching)
  - Headered ROM detection (iNES, SNES, etc.)

Reports:
  - verified: ROM matches DAT hash
  - bad_hash: ROM exists but hash differs
  - missing:  ROM in DAT but not on disk
  - extra:    ROM on disk but not in DAT
"""
from __future__ import annotations

import binascii
import hashlib
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit

log = get_logger("rom_audit")

# Header sizes for headered ROM formats (bytes to skip for hash)
HEADER_SIZES = {
    ".nes": 16,   # iNES header
    ".fds": 16,   # FDS header
    ".lnx": 64,   # Atari Lynx header
    ".a78": 128,  # Atari 7800 header
    ".smc": 512,  # SNES copier header (if file size % 1024 == 512)
}


# ═══════════════════════════════════════════════════════════════════════
# Hashing
# ═══════════════════════════════════════════════════════════════════════

def hash_file_crc32(filepath: Path, skip_header: int = 0) -> str:
    """Compute CRC32 of a file, optionally skipping a header.

    Returns lowercase hex string (8 chars, zero-padded).
    """
    crc = 0
    try:
        with open(filepath, "rb") as fh:
            if skip_header > 0:
                fh.seek(skip_header)
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                crc = binascii.crc32(chunk, crc)
        return f"{crc & 0xFFFFFFFF:08x}"
    except (OSError, PermissionError) as exc:
        log.warning("CRC32 failed for %s: %s", filepath, exc)
        return ""


def hash_file_sha1(filepath: Path, skip_header: int = 0) -> str:
    """Compute SHA1 of a file, optionally skipping a header.

    Returns lowercase hex string (40 chars).
    """
    h = hashlib.sha1()
    try:
        with open(filepath, "rb") as fh:
            if skip_header > 0:
                fh.seek(skip_header)
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError) as exc:
        log.warning("SHA1 failed for %s: %s", filepath, exc)
        return ""


def _detect_header_skip(filepath: Path) -> int:
    """Detect if a ROM file has a copier/format header to skip."""
    ext = filepath.suffix.lower()
    if ext == ".smc":
        try:
            size = filepath.stat().st_size
            if size % 1024 == 512:
                return 512
        except OSError:
            pass
        return 0
    return HEADER_SIZES.get(ext, 0)


def hash_rom(filepath: Path, algorithm: str = "crc32") -> str:
    """Hash a ROM file with auto header detection.

    Args:
        filepath: Path to ROM file.
        algorithm: 'crc32' or 'sha1'.
    """
    skip = _detect_header_skip(filepath)
    if algorithm == "crc32":
        return hash_file_crc32(filepath, skip_header=skip)
    elif algorithm == "sha1":
        return hash_file_sha1(filepath, skip_header=skip)
    raise ValueError(f"Unsupported algorithm: {algorithm}")


def hash_zip_contents(zip_path: Path) -> list[dict[str, str]]:
    """Hash every file inside a ZIP archive. Returns list of {name, crc32, sha1, size}."""
    results: list[dict[str, str]] = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                crc_hex = f"{info.CRC & 0xFFFFFFFF:08x}"
                # SHA1 requires reading the data
                sha1_hex = ""
                try:
                    data = zf.read(info.filename)
                    sha1_hex = hashlib.sha1(data).hexdigest()
                except Exception:
                    pass
                results.append({
                    "name": info.filename,
                    "crc32": crc_hex,
                    "sha1": sha1_hex,
                    "size": str(info.file_size),
                })
    except (zipfile.BadZipFile, OSError) as exc:
        log.warning("Cannot read ZIP %s: %s", zip_path, exc)
    return results


# ═══════════════════════════════════════════════════════════════════════
# DAT file parsing
# ═══════════════════════════════════════════════════════════════════════

class DATEntry:
    """A single ROM entry from a DAT file."""
    __slots__ = ("game_name", "rom_name", "size", "crc32", "sha1", "md5", "status")

    def __init__(self, game_name: str, rom_name: str, size: int = 0,
                 crc32: str = "", sha1: str = "", md5: str = "", status: str = ""):
        self.game_name = game_name
        self.rom_name = rom_name
        self.size = size
        self.crc32 = crc32.lower().lstrip("0x") if crc32 else ""
        self.sha1 = sha1.lower() if sha1 else ""
        self.md5 = md5.lower() if md5 else ""
        self.status = status  # "baddump", "nodump", or ""

    def __repr__(self) -> str:
        return f"DATEntry({self.game_name}/{self.rom_name} crc={self.crc32})"


def parse_dat_file(dat_path: Path) -> list[DATEntry]:
    """Auto-detect DAT format and parse.

    Supports:
      - CLRMamePro text format
      - MAME XML format (<mame>/<machine>/<rom>)
      - Logiqx XML format (<datafile>/<game>/<rom>)
    """
    dat_path = Path(dat_path)
    if not dat_path.exists():
        log.error("DAT file not found: %s", dat_path)
        return []

    content = dat_path.read_text(encoding="utf-8", errors="replace")

    # Detect format
    if content.lstrip().startswith("<?xml") or content.lstrip().startswith("<"):
        return _parse_dat_xml(dat_path, content)
    elif "clrmamepro" in content[:500].lower() or "game (" in content[:2000].lower():
        return _parse_dat_clrmamepro(content)
    else:
        log.warning("Unknown DAT format: %s", dat_path)
        return []


def _parse_dat_xml(dat_path: Path, content: str) -> list[DATEntry]:
    """Parse XML-format DAT (MAME XML or Logiqx datafile)."""
    entries: list[DATEntry] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        log.error("XML parse error in %s: %s", dat_path, exc)
        return entries

    # MAME XML: <mame><machine name="..."><rom name="..." size="..." crc="..." sha1="..."/></machine></mame>
    # Logiqx:   <datafile><game name="..."><rom name="..." size="..." crc="..." sha1="..."/></game></datafile>
    for game_tag in ("machine", "game", "software"):
        for game_el in root.iter(game_tag):
            game_name = game_el.get("name", "")
            for rom_el in game_el.iter("rom"):
                rom_name = rom_el.get("name", "")
                size_str = rom_el.get("size", "0")
                try:
                    size = int(size_str)
                except ValueError:
                    size = 0
                entries.append(DATEntry(
                    game_name=game_name,
                    rom_name=rom_name,
                    size=size,
                    crc32=rom_el.get("crc", ""),
                    sha1=rom_el.get("sha1", ""),
                    md5=rom_el.get("md5", ""),
                    status=rom_el.get("status", ""),
                ))

    log.info("Parsed %d ROM entries from XML DAT: %s", len(entries), dat_path.name)
    return entries


def _parse_dat_clrmamepro(content: str) -> list[DATEntry]:
    """Parse CLRMamePro text-format DAT file."""
    entries: list[DATEntry] = []

    # Match game blocks: game ( ... )
    game_pattern = re.compile(
        r'game\s*\(\s*name\s+"([^"]+)".*?\)', re.DOTALL | re.IGNORECASE
    )
    rom_pattern = re.compile(
        r'rom\s*\(\s*'
        r'name\s+"([^"]+)"\s*'
        r'(?:size\s+(\d+)\s*)?'
        r'(?:crc\s+([0-9a-fA-F]+)\s*)?'
        r'(?:md5\s+([0-9a-fA-F]+)\s*)?'
        r'(?:sha1\s+([0-9a-fA-F]+)\s*)?'
        r'(?:status\s+(\w+)\s*)?'
        r'\)',
        re.IGNORECASE,
    )

    # Simpler approach: find all game blocks
    current_game = ""
    for line in content.splitlines():
        stripped = line.strip()

        # Game name
        name_match = re.match(r'^\s*name\s+"([^"]+)"', stripped)
        if name_match:
            current_game = name_match.group(1)
            continue

        # ROM entry
        rom_match = re.match(
            r'^\s*rom\s*\(\s*name\s+"([^"]+)"\s*'
            r'(?:size\s+(\d+)\s*)?'
            r'(?:crc\s+([0-9a-fA-F]+)\s*)?'
            r'(?:md5\s+([0-9a-fA-F]+)\s*)?'
            r'(?:sha1\s+([0-9a-fA-F]+)\s*)?',
            stripped, re.IGNORECASE,
        )
        if rom_match and current_game:
            entries.append(DATEntry(
                game_name=current_game,
                rom_name=rom_match.group(1),
                size=int(rom_match.group(2)) if rom_match.group(2) else 0,
                crc32=rom_match.group(3) or "",
                md5=rom_match.group(4) or "",
                sha1=rom_match.group(5) or "",
            ))

    log.info("Parsed %d ROM entries from CLRMamePro DAT", len(entries))
    return entries


# ═══════════════════════════════════════════════════════════════════════
# Verification engine
# ═══════════════════════════════════════════════════════════════════════

class VerifyResult:
    """Result for a single ROM verification."""
    __slots__ = ("game_name", "rom_name", "status", "expected_crc", "actual_crc",
                 "expected_sha1", "actual_sha1", "filepath", "detail")

    STATUS_VERIFIED = "verified"
    STATUS_BAD_HASH = "bad_hash"
    STATUS_MISSING  = "missing"
    STATUS_EXTRA    = "extra"

    def __init__(self, **kwargs: Any):
        for k, v in kwargs.items():
            setattr(self, k, v)
        for slot in self.__slots__:
            if not hasattr(self, slot):
                setattr(self, slot, "")

    def to_dict(self) -> dict[str, str]:
        return {s: getattr(self, s, "") for s in self.__slots__}


def verify_roms(
    rom_dir: str | Path,
    dat_path: str | Path,
    *,
    use_sha1: bool = False,
    zip_mode: bool = True,
    system_name: str = "",
) -> dict[str, Any]:
    """Verify ROMs in rom_dir against entries in dat_path.

    Args:
        rom_dir:     Directory containing ROM files (zips or loose).
        dat_path:    Path to the DAT/XML file with expected hashes.
        use_sha1:    If True, verify SHA1 as well as CRC32.
        zip_mode:    If True, verify contents inside ZIP files.
        system_name: Optional system name for logging.

    Returns:
        {
          "system": str,
          "dat_file": str,
          "total_in_dat": int,
          "verified": int,
          "bad_hash": int,
          "missing": int,
          "extra": int,
          "completeness_pct": float,
          "results": list[dict],
        }
    """
    rom_dir = Path(rom_dir)
    dat_path = Path(dat_path)

    log.info("ROM audit: %s against %s", rom_dir, dat_path.name)

    # Parse DAT
    dat_entries = parse_dat_file(dat_path)
    if not dat_entries:
        return {
            "system": system_name,
            "dat_file": str(dat_path),
            "error": "No entries parsed from DAT file",
            "total_in_dat": 0,
        }

    # Build lookup: game_name -> {rom_name -> DATEntry}
    dat_lookup: dict[str, dict[str, DATEntry]] = defaultdict(dict)
    for entry in dat_entries:
        dat_lookup[entry.game_name][entry.rom_name] = entry

    # Also build flat CRC lookup for quick matching
    crc_lookup: dict[str, DATEntry] = {}
    for entry in dat_entries:
        if entry.crc32:
            crc_lookup[entry.crc32] = entry

    # Scan ROM directory
    results: list[VerifyResult] = []
    verified_games: set[str] = set()
    scanned_games: set[str] = set()

    if not rom_dir.exists():
        log.warning("ROM directory does not exist: %s", rom_dir)
    else:
        for fpath in sorted(rom_dir.iterdir()):
            if not fpath.is_file():
                continue

            game_stem = fpath.stem
            scanned_games.add(game_stem)

            # ZIP mode: verify inner files
            if zip_mode and fpath.suffix.lower() == ".zip":
                inner_hashes = hash_zip_contents(fpath)
                if game_stem in dat_lookup:
                    expected_roms = dat_lookup[game_stem]
                    matched_inner: set[str] = set()

                    for inner in inner_hashes:
                        rom_name = inner["name"]
                        if rom_name in expected_roms:
                            exp = expected_roms[rom_name]
                            matched_inner.add(rom_name)
                            crc_ok = (not exp.crc32) or (inner["crc32"] == exp.crc32)
                            sha1_ok = (not use_sha1) or (not exp.sha1) or (inner["sha1"] == exp.sha1)

                            if crc_ok and sha1_ok:
                                results.append(VerifyResult(
                                    game_name=game_stem, rom_name=rom_name,
                                    status=VerifyResult.STATUS_VERIFIED,
                                    expected_crc=exp.crc32, actual_crc=inner["crc32"],
                                    expected_sha1=exp.sha1, actual_sha1=inner["sha1"],
                                    filepath=str(fpath),
                                ))
                                verified_games.add(game_stem)
                            else:
                                detail_parts = []
                                if not crc_ok:
                                    detail_parts.append(f"CRC expected={exp.crc32} actual={inner['crc32']}")
                                if not sha1_ok:
                                    detail_parts.append(f"SHA1 expected={exp.sha1} actual={inner['sha1']}")
                                results.append(VerifyResult(
                                    game_name=game_stem, rom_name=rom_name,
                                    status=VerifyResult.STATUS_BAD_HASH,
                                    expected_crc=exp.crc32, actual_crc=inner["crc32"],
                                    expected_sha1=exp.sha1, actual_sha1=inner["sha1"],
                                    filepath=str(fpath),
                                    detail="; ".join(detail_parts),
                                ))

                    # Check for missing inner ROMs
                    for rom_name in expected_roms:
                        if rom_name not in matched_inner:
                            exp = expected_roms[rom_name]
                            if exp.status == "nodump":
                                continue
                            results.append(VerifyResult(
                                game_name=game_stem, rom_name=rom_name,
                                status=VerifyResult.STATUS_MISSING,
                                expected_crc=exp.crc32,
                                detail=f"Missing from ZIP: {fpath.name}",
                            ))
                else:
                    # ZIP game not in DAT — match by CRC
                    any_match = False
                    for inner in inner_hashes:
                        if inner["crc32"] in crc_lookup:
                            any_match = True
                            break
                    if not any_match:
                        results.append(VerifyResult(
                            game_name=game_stem, rom_name=fpath.name,
                            status=VerifyResult.STATUS_EXTRA,
                            filepath=str(fpath),
                            detail="Not in DAT file",
                        ))

            else:
                # Loose ROM file
                actual_crc = hash_rom(fpath, "crc32")
                actual_sha1 = hash_rom(fpath, "sha1") if use_sha1 else ""

                if game_stem in dat_lookup:
                    # Try to match by name or CRC within the game
                    matched = False
                    for rom_name, exp in dat_lookup[game_stem].items():
                        if exp.crc32 and actual_crc == exp.crc32:
                            sha1_ok = (not use_sha1) or (not exp.sha1) or (actual_sha1 == exp.sha1)
                            results.append(VerifyResult(
                                game_name=game_stem, rom_name=rom_name,
                                status=VerifyResult.STATUS_VERIFIED if sha1_ok else VerifyResult.STATUS_BAD_HASH,
                                expected_crc=exp.crc32, actual_crc=actual_crc,
                                expected_sha1=exp.sha1, actual_sha1=actual_sha1,
                                filepath=str(fpath),
                            ))
                            verified_games.add(game_stem)
                            matched = True
                            break
                    if not matched:
                        # CRC mismatch for all entries in this game
                        first_exp = next(iter(dat_lookup[game_stem].values()))
                        results.append(VerifyResult(
                            game_name=game_stem, rom_name=fpath.name,
                            status=VerifyResult.STATUS_BAD_HASH,
                            expected_crc=first_exp.crc32, actual_crc=actual_crc,
                            filepath=str(fpath),
                            detail="CRC mismatch",
                        ))
                elif actual_crc in crc_lookup:
                    # Loose file matches a known CRC
                    exp = crc_lookup[actual_crc]
                    results.append(VerifyResult(
                        game_name=exp.game_name, rom_name=fpath.name,
                        status=VerifyResult.STATUS_VERIFIED,
                        expected_crc=exp.crc32, actual_crc=actual_crc,
                        filepath=str(fpath),
                        detail=f"Matched by CRC to {exp.game_name}/{exp.rom_name}",
                    ))
                    verified_games.add(exp.game_name)
                else:
                    results.append(VerifyResult(
                        game_name=game_stem, rom_name=fpath.name,
                        status=VerifyResult.STATUS_EXTRA,
                        actual_crc=actual_crc,
                        filepath=str(fpath),
                        detail="Not in DAT file",
                    ))

    # Find games in DAT but not on disk
    dat_game_names = set(dat_lookup.keys())
    for missing_game in dat_game_names - scanned_games:
        for rom_name, exp in dat_lookup[missing_game].items():
            if exp.status == "nodump":
                continue
            results.append(VerifyResult(
                game_name=missing_game, rom_name=rom_name,
                status=VerifyResult.STATUS_MISSING,
                expected_crc=exp.crc32,
                detail="Game not found on disk",
            ))

    # Summarize
    counts = defaultdict(int)
    for r in results:
        counts[r.status] += 1

    total_games_in_dat = len(dat_game_names)
    completeness = round(len(verified_games) / total_games_in_dat * 100, 1) if total_games_in_dat else 0

    summary = {
        "system": system_name or rom_dir.name,
        "dat_file": str(dat_path),
        "total_in_dat": total_games_in_dat,
        "total_roms_in_dat": len(dat_entries),
        "verified": counts[VerifyResult.STATUS_VERIFIED],
        "bad_hash": counts[VerifyResult.STATUS_BAD_HASH],
        "missing": counts[VerifyResult.STATUS_MISSING],
        "extra": counts[VerifyResult.STATUS_EXTRA],
        "completeness_pct": completeness,
        "results": [r.to_dict() for r in results],
    }

    log.info(
        "ROM audit complete: %s — verified=%d bad=%d missing=%d extra=%d (%.1f%% complete)",
        system_name or rom_dir.name,
        summary["verified"], summary["bad_hash"],
        summary["missing"], summary["extra"],
        completeness,
    )
    audit("rom_audit", system_name or str(rom_dir), {
        k: v for k, v in summary.items() if k != "results"
    })

    return summary


# ═══════════════════════════════════════════════════════════════════════
# Batch verification
# ═══════════════════════════════════════════════════════════════════════

def verify_all_systems(
    dat_dir: Optional[str | Path] = None,
    use_sha1: bool = False,
) -> dict[str, Any]:
    """Verify all systems that have both a ROM directory and a DAT file.

    Args:
        dat_dir: Directory containing DAT files (default: config paths.dat_root).
        use_sha1: Also verify SHA1 hashes.

    Returns:
        {
          "systems": {name: verify_result},
          "total_verified": int,
          "total_bad": int,
          "total_missing": int,
        }
    """
    hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    if dat_dir is None:
        dat_dir = Path(cfg_get("paths.dat_root", str(hs_root / "DATs")))
    else:
        dat_dir = Path(dat_dir)

    log.info("Batch ROM verification — DAT dir: %s", dat_dir)

    results: dict[str, Any] = {"systems": {}}
    totals = {"verified": 0, "bad_hash": 0, "missing": 0, "extra": 0}

    if not dat_dir.exists():
        log.warning("DAT directory not found: %s", dat_dir)
        return {**results, **totals, "error": f"DAT directory not found: {dat_dir}"}

    # Map DAT files to system names
    for dat_file in sorted(dat_dir.glob("*.dat")):
        system_name = dat_file.stem
        rom_dir = hs_root / system_name

        if not rom_dir.exists():
            # Try alternate locations
            alt = hs_root / system_name / "roms"
            if alt.exists():
                rom_dir = alt

        if not rom_dir.exists():
            continue

        result = verify_roms(
            rom_dir, dat_file,
            use_sha1=use_sha1,
            system_name=system_name,
        )
        results["systems"][system_name] = {
            k: v for k, v in result.items() if k != "results"
        }
        for key in totals:
            totals[key] += result.get(key, 0)

    # Also check XML-format DATs
    for dat_file in sorted(dat_dir.glob("*.xml")):
        system_name = dat_file.stem
        if system_name in results["systems"]:
            continue
        rom_dir = hs_root / system_name
        if not rom_dir.exists():
            continue

        result = verify_roms(
            rom_dir, dat_file,
            use_sha1=use_sha1,
            system_name=system_name,
        )
        results["systems"][system_name] = {
            k: v for k, v in result.items() if k != "results"
        }
        for key in totals:
            totals[key] += result.get(key, 0)

    results.update(totals)
    results["systems_checked"] = len(results["systems"])

    log.info(
        "Batch ROM verification complete: %d systems, verified=%d bad=%d missing=%d extra=%d",
        results["systems_checked"], totals["verified"], totals["bad_hash"],
        totals["missing"], totals["extra"],
    )

    return results
