"""
M65 -- Game List Extractor Engine
Extract game lists from any KINHANK HDD variant and output standardized CSV.

Supports:
  - Variant A: HyperSpin XML databases
  - Variant B-A: AttractMode romlists (.txt)
  - Variant B-C: CORE - TYPE R embedded frontends (dir scan)
  - Variant C-B: Batocera boot (game list files)
  - Variant C-D: Batocera data (ROM directory scan)
"""

import csv
import os
import re
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

logger = logging.getLogger("gamelist_extractor")


@dataclass
class GameEntry:
    """Standardized game entry across all variants."""
    name: str
    system: str
    source: str = ""          # which frontend/romlist it came from
    year: str = ""
    manufacturer: str = ""
    genre: str = ""
    players: str = ""
    rating: str = ""
    rom_name: str = ""        # filename without extension
    rom_path: str = ""        # full path if available
    file_size_mb: float = 0.0
    variant: str = ""         # A, B-A, B-C, C-B, C-D


@dataclass
class ExtractionResult:
    """Result of a game list extraction."""
    drive_letter: str
    variant: str
    systems: int = 0
    games: int = 0
    entries: List[GameEntry] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_csv(self, output_path: str) -> str:
        """Write game list to CSV file. Returns the path written."""
        if not self.entries:
            logger.warning("No entries to write")
            return ""

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fieldnames = [
            "name", "system", "source", "year", "manufacturer",
            "genre", "players", "rating", "rom_name", "rom_path",
            "file_size_mb", "variant"
        ]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for entry in self.entries:
                writer.writerow(asdict(entry))
        logger.info("Wrote %d entries to %s", len(self.entries), output_path)
        return output_path

    def summary(self) -> str:
        lines = [
            f"Drive {self.drive_letter} -- Variant {self.variant}",
            f"  Systems: {self.systems} | Games: {self.games}",
        ]
        if self.errors:
            lines.append(f"  Errors: {len(self.errors)}")
        if self.warnings:
            lines.append(f"  Warnings: {len(self.warnings)}")

        # Top 10 systems by game count
        sys_counts: Dict[str, int] = {}
        for e in self.entries:
            sys_counts[e.system] = sys_counts.get(e.system, 0) + 1
        top = sorted(sys_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        if top:
            lines.append("  Top systems:")
            for sys_name, count in top:
                lines.append(f"    {count:>6} | {sys_name}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Variant A: HyperSpin XML Database Parser
# ---------------------------------------------------------------------------

def extract_hyperspin_xml(drive_root: str) -> ExtractionResult:
    """Extract game list from HyperSpin XML databases (Variant A)."""
    result = ExtractionResult(
        drive_letter=drive_root[:2],
        variant="A",
    )
    db_path = os.path.join(drive_root, "Arcade", "Databases")
    if not os.path.isdir(db_path):
        result.errors.append(f"Database path not found: {db_path}")
        return result

    systems_processed = 0
    for sys_entry in sorted(os.scandir(db_path), key=lambda e: e.name):
        if not sys_entry.is_dir():
            continue
        sys_name = sys_entry.name

        # Find the main XML file
        xml_file = os.path.join(db_path, sys_name, f"{sys_name}.xml")
        if not os.path.isfile(xml_file):
            # Try largest XML in the folder
            xmls = [f for f in os.listdir(sys_entry.path) if f.endswith(".xml")]
            if xmls:
                xml_file = os.path.join(
                    sys_entry.path,
                    max(xmls, key=lambda f: os.path.getsize(os.path.join(sys_entry.path, f)))
                )
            else:
                continue

        games = _parse_hyperspin_xml(xml_file, sys_name)
        if games:
            result.entries.extend(games)
            systems_processed += 1

    result.systems = systems_processed
    result.games = len(result.entries)
    return result


def _parse_hyperspin_xml(xml_path: str, system_name: str) -> List[GameEntry]:
    """Parse a single HyperSpin XML database file."""
    entries = []
    try:
        # HyperSpin XMLs can be malformed; use iterparse with error recovery
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        # Quick regex extraction for speed on large files
        for match in re.finditer(
            r'<game name="([^"]*)"[^>]*>.*?</game>',
            content, re.DOTALL
        ):
            block = match.group(0)
            name = match.group(1)

            desc = _xml_tag(block, "description") or name
            year = _xml_tag(block, "year") or ""
            manufacturer = _xml_tag(block, "manufacturer") or ""
            genre = _xml_tag(block, "genre") or ""
            players = _xml_tag(block, "players") or ""
            rating = _xml_tag(block, "rating") or ""

            entries.append(GameEntry(
                name=desc,
                system=system_name,
                source="HyperSpin XML",
                year=year,
                manufacturer=manufacturer,
                genre=genre,
                players=players,
                rating=rating,
                rom_name=name,
                variant="A",
            ))
    except Exception as e:
        logger.warning("Error parsing %s: %s", xml_path, e)

    return entries


def _xml_tag(block: str, tag: str) -> Optional[str]:
    """Extract text content of a tag from an XML block."""
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Variant B-A: AttractMode Romlist Parser
# ---------------------------------------------------------------------------

def extract_attractmode_romlists(drive_root: str) -> ExtractionResult:
    """Extract game list from AttractMode romlists (Variant B-A)."""
    result = ExtractionResult(
        drive_letter=drive_root[:2],
        variant="B-A",
    )
    romlist_path = os.path.join(drive_root, "Arcade", "romlists")
    if not os.path.isdir(romlist_path):
        result.errors.append(f"Romlists path not found: {romlist_path}")
        return result

    # Meta/aggregate lists to skip
    skip_patterns = re.compile(r'^(--|^All |Collections$|BEIFEN|Settings)', re.IGNORECASE)

    systems_processed = 0
    for entry in sorted(os.scandir(romlist_path), key=lambda e: e.name):
        if not entry.is_file() or not entry.name.endswith(".txt"):
            continue
        sys_name = entry.name[:-4]  # strip .txt

        if skip_patterns.search(sys_name):
            continue

        games = _parse_romlist(entry.path, sys_name)
        if games:
            result.entries.extend(games)
            systems_processed += 1

    result.systems = systems_processed
    result.games = len(result.entries)
    return result


def _parse_romlist(romlist_path: str, system_name: str) -> List[GameEntry]:
    """Parse a single AttractMode romlist .txt file.

    Format: romname;title;emulator;cloneof;year;manufacturer;category;players;rotation;control;status;displaycount;displaytype;altromname;alttitle;extra;buttons
    """
    entries = []
    try:
        with open(romlist_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(";")
                if len(parts) < 2:
                    continue

                rom_name = parts[0].strip()
                title = parts[1].strip() if len(parts) > 1 else rom_name
                year = parts[4].strip() if len(parts) > 4 else ""
                manufacturer = parts[5].strip() if len(parts) > 5 else ""
                genre = parts[6].strip() if len(parts) > 6 else ""
                players = parts[7].strip() if len(parts) > 7 else ""

                entries.append(GameEntry(
                    name=title or rom_name,
                    system=system_name,
                    source="AttractMode romlist",
                    year=year,
                    manufacturer=manufacturer,
                    genre=genre,
                    players=players,
                    rom_name=rom_name,
                    variant="B-A",
                ))
    except Exception as e:
        logger.warning("Error parsing romlist %s: %s", romlist_path, e)

    return entries


# ---------------------------------------------------------------------------
# Variant B-C: CORE - TYPE R Directory Scanner
# ---------------------------------------------------------------------------

def extract_core_type_r(drive_root: str) -> ExtractionResult:
    """Extract game list from CORE - TYPE R hub (Variant B-C)."""
    result = ExtractionResult(
        drive_letter=drive_root[:2],
        variant="B-C",
    )
    core_path = os.path.join(drive_root, "CORE - TYPE R", "collections", "COMPUTERS", "roms")
    if not os.path.isdir(core_path):
        result.errors.append(f"CORE path not found: {core_path}")
        return result

    # Scan each embedded frontend
    frontends = {
        "Playnite": "PC Games",
        "LaunchBox": "Games",
        "HyperSpin Attraction": "collections",
        "Hyperspin TeknoParrot": "collections",
        "RetroBat": "roms",
    }

    systems_processed = 0
    for fe_name, content_dir in frontends.items():
        fe_path = os.path.join(core_path, fe_name)
        if not os.path.isdir(fe_path):
            continue

        content_path = os.path.join(fe_path, content_dir)
        if not os.path.isdir(content_path):
            result.warnings.append(f"{fe_name}: no {content_dir}/ directory")
            continue

        if fe_name == "Playnite":
            # PC games - each subdir is a game
            games = _scan_playnite_games(content_path, fe_name)
            result.entries.extend(games)
            systems_processed += 1

        elif fe_name == "LaunchBox":
            # Each subdir under Games/ is a system
            for sys_entry in sorted(os.scandir(content_path), key=lambda e: e.name):
                if sys_entry.is_dir():
                    game_count = _count_game_files(sys_entry.path)
                    if game_count > 0:
                        for game_file in _list_game_files(sys_entry.path):
                            result.entries.append(GameEntry(
                                name=Path(game_file).stem,
                                system=sys_entry.name,
                                source=f"LaunchBox/{sys_entry.name}",
                                rom_name=Path(game_file).stem,
                                rom_path=game_file,
                                file_size_mb=round(os.path.getsize(game_file) / (1024*1024), 1),
                                variant="B-C",
                            ))
                        systems_processed += 1

        elif fe_name in ("HyperSpin Attraction", "Hyperspin TeknoParrot"):
            # Each subdir under collections/ is a system
            for sys_entry in sorted(os.scandir(content_path), key=lambda e: e.name):
                if sys_entry.is_dir() and sys_entry.name != "Settings":
                    # Just record the system with a count
                    rom_dir = os.path.join(sys_entry.path, "roms")
                    if os.path.isdir(rom_dir):
                        for game_file in _list_game_files(rom_dir):
                            result.entries.append(GameEntry(
                                name=Path(game_file).stem,
                                system=sys_entry.name,
                                source=fe_name,
                                rom_name=Path(game_file).stem,
                                rom_path=game_file,
                                file_size_mb=round(os.path.getsize(game_file) / (1024*1024), 1),
                                variant="B-C",
                            ))
                    systems_processed += 1

        elif fe_name == "RetroBat":
            for sys_entry in sorted(os.scandir(content_path), key=lambda e: e.name):
                if sys_entry.is_dir():
                    game_count = _count_game_files(sys_entry.path)
                    if game_count > 0:
                        # Only record count, not individual files (too many)
                        result.entries.append(GameEntry(
                            name=f"[{game_count} ROMs]",
                            system=sys_entry.name,
                            source="RetroBat",
                            variant="B-C",
                        ))
                        systems_processed += 1

    result.systems = systems_processed
    result.games = len(result.entries)
    return result


def _scan_playnite_games(pc_games_path: str, source: str) -> List[GameEntry]:
    """Scan Playnite PC Games directory."""
    entries = []
    if not os.path.isdir(pc_games_path):
        return entries
    for game_dir in sorted(os.scandir(pc_games_path), key=lambda e: e.name):
        if game_dir.is_dir():
            # Calculate total size
            total_size = 0
            try:
                for root, dirs, files in os.walk(game_dir.path):
                    for f in files:
                        try:
                            total_size += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
                    break  # only first level for speed
            except OSError:
                pass

            entries.append(GameEntry(
                name=game_dir.name,
                system="PC",
                source=source,
                rom_name=game_dir.name,
                rom_path=game_dir.path,
                file_size_mb=round(total_size / (1024*1024), 1),
                variant="B-C",
            ))
    return entries


# ---------------------------------------------------------------------------
# Variant C-D: Batocera ROM Directory Scanner
# ---------------------------------------------------------------------------

def extract_batocera_roms(drive_root: str) -> ExtractionResult:
    """Extract game list from Batocera data partition (Variant C-D)."""
    result = ExtractionResult(
        drive_letter=drive_root[:2],
        variant="C-D",
    )
    roms_path = os.path.join(drive_root, "roms")
    if not os.path.isdir(roms_path):
        result.errors.append(f"ROMs path not found: {roms_path}")
        return result

    systems_processed = 0
    for sys_entry in sorted(os.scandir(roms_path), key=lambda e: e.name):
        if not sys_entry.is_dir():
            continue
        sys_name = sys_entry.name
        game_files = _list_game_files(sys_entry.path)

        if game_files:
            for gf in game_files:
                result.entries.append(GameEntry(
                    name=Path(gf).stem,
                    system=sys_name,
                    source="Batocera/roms",
                    rom_name=Path(gf).stem,
                    rom_path=gf,
                    file_size_mb=round(os.path.getsize(gf) / (1024*1024), 1),
                    variant="C-D",
                ))
            systems_processed += 1

    result.systems = systems_processed
    result.games = len(result.entries)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Common game file extensions
GAME_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".iso", ".bin", ".cue", ".img", ".chd",
    ".nsp", ".xci", ".nsz", ".cia", ".3ds", ".nds",
    ".gba", ".gbc", ".gb", ".nes", ".sfc", ".smc",
    ".n64", ".z64", ".v64", ".gcm", ".rvz", ".wbfs", ".wad",
    ".pkg", ".vpk", ".pbp", ".cso", ".ecm",
    ".rom", ".a26", ".a78", ".lnx", ".ngp", ".ngc",
    ".pce", ".sgx", ".md", ".sms", ".gg",
    ".col", ".sg", ".sc", ".ws", ".wsc",
    ".exe", ".lnk", ".bat", ".cmd",
}


def _list_game_files(directory: str, max_files: int = 500) -> List[str]:
    """List game files in a directory (non-recursive)."""
    files = []
    try:
        for entry in os.scandir(directory):
            if entry.is_file():
                ext = Path(entry.name).suffix.lower()
                if ext in GAME_EXTENSIONS:
                    files.append(entry.path)
                    if len(files) >= max_files:
                        break
    except OSError:
        pass
    return files


def _count_game_files(directory: str) -> int:
    """Count game files in a directory (non-recursive)."""
    count = 0
    try:
        for entry in os.scandir(directory):
            if entry.is_file():
                ext = Path(entry.name).suffix.lower()
                if ext in GAME_EXTENSIONS:
                    count += 1
    except OSError:
        pass
    return count


# ---------------------------------------------------------------------------
# Auto-detect and extract
# ---------------------------------------------------------------------------

def extract_gamelist(drive_letter: str, variant: Optional[str] = None) -> ExtractionResult:
    """
    Auto-detect variant and extract game list from a drive.

    Args:
        drive_letter: Drive letter like "D", "K:", etc.
        variant: Force a specific variant (A, B-A, B-C, C-B, C-D) or auto-detect.
    """
    drive = drive_letter.strip().rstrip(":\\")
    drive_root = f"{drive}:\\"

    if not os.path.exists(drive_root):
        result = ExtractionResult(drive_letter=f"{drive}:", variant=variant or "?")
        result.errors.append(f"Drive {drive}: not accessible")
        return result

    # Auto-detect variant if not specified
    if not variant:
        from engines.drive_fingerprint import fingerprint_drive
        fp = fingerprint_drive(drive)
        variant = fp.variant

    if variant == "A":
        return extract_hyperspin_xml(drive_root)
    elif variant == "B-A":
        return extract_attractmode_romlists(drive_root)
    elif variant == "B-C":
        return extract_core_type_r(drive_root)
    elif variant == "C-D":
        return extract_batocera_roms(drive_root)
    elif variant == "C-B":
        # Boot partition has no games
        result = ExtractionResult(drive_letter=f"{drive}:", variant="C-B")
        result.warnings.append("Batocera boot partition has no game content")
        return result
    else:
        result = ExtractionResult(drive_letter=f"{drive}:", variant=variant or "?")
        result.errors.append(f"Unknown variant: {variant}")
        return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python gamelist_extractor.py <drive_letter> [output.csv] [variant]")
        print("  Examples:")
        print("    python gamelist_extractor.py D")
        print("    python gamelist_extractor.py K gamelist_k.csv")
        print("    python gamelist_extractor.py L gamelist_l.csv B-C")
        sys.exit(1)

    drive = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else f"gamelist_{drive.strip(':')}.csv"
    forced_variant = sys.argv[3] if len(sys.argv) > 3 else None

    logging.basicConfig(level=logging.INFO)
    result = extract_gamelist(drive, forced_variant)
    print(result.summary())
    if result.entries:
        result.to_csv(output)
        print(f"\nSaved to: {output}")
