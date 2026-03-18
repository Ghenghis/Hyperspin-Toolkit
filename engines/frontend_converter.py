"""
M58 -- Cross-Frontend Import/Export Engine
Convert game lists between frontend formats:
  - HyperSpin XML databases
  - AttractMode romlists (.txt)
  - LaunchBox XML (Platforms + Games)
  - Batocera gamelist.xml
  - Playnite library (YAML/DB)
  - Generic CSV (M65 standardized format)

Uses the GameEntry dataclass from M65 as the universal interchange format.
"""

import csv
import os
import re
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Dict

from engines.gamelist_extractor import GameEntry

logger = logging.getLogger("frontend_converter")


# ---------------------------------------------------------------------------
# Import: Read from various frontend formats -> List[GameEntry]
# ---------------------------------------------------------------------------

def import_hyperspin_xml(xml_path: str, system_name: str = "") -> List[GameEntry]:
    """Import games from a HyperSpin XML database file."""
    if not system_name:
        system_name = Path(xml_path).stem
    entries = []
    try:
        with open(xml_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for match in re.finditer(
            r'<game name="([^"]*)"[^>]*>.*?</game>', content, re.DOTALL
        ):
            block = match.group(0)
            rom_name = match.group(1)
            entries.append(GameEntry(
                name=_xtag(block, "description") or rom_name,
                system=system_name,
                source="HyperSpin XML",
                year=_xtag(block, "year") or "",
                manufacturer=_xtag(block, "manufacturer") or "",
                genre=_xtag(block, "genre") or "",
                players=_xtag(block, "players") or "",
                rating=_xtag(block, "rating") or "",
                rom_name=rom_name,
                variant="A",
            ))
    except Exception as e:
        logger.error("Failed to import HyperSpin XML %s: %s", xml_path, e)
    return entries


def import_attractmode_romlist(romlist_path: str, system_name: str = "") -> List[GameEntry]:
    """Import games from an AttractMode romlist .txt file."""
    if not system_name:
        system_name = Path(romlist_path).stem
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
                entries.append(GameEntry(
                    name=parts[1].strip() if len(parts) > 1 else parts[0].strip(),
                    system=system_name,
                    source="AttractMode romlist",
                    year=parts[4].strip() if len(parts) > 4 else "",
                    manufacturer=parts[5].strip() if len(parts) > 5 else "",
                    genre=parts[6].strip() if len(parts) > 6 else "",
                    players=parts[7].strip() if len(parts) > 7 else "",
                    rom_name=parts[0].strip(),
                    variant="B-A",
                ))
    except Exception as e:
        logger.error("Failed to import romlist %s: %s", romlist_path, e)
    return entries


def import_launchbox_xml(platform_xml_path: str) -> List[GameEntry]:
    """Import games from a LaunchBox Platform XML file."""
    entries = []
    try:
        tree = ET.parse(platform_xml_path)
        root = tree.getroot()
        for game in root.findall(".//Game"):
            title = _el_text(game, "Title") or ""
            if not title:
                continue
            entries.append(GameEntry(
                name=title,
                system=_el_text(game, "Platform") or Path(platform_xml_path).stem,
                source="LaunchBox XML",
                year=(_el_text(game, "ReleaseDate") or "")[:4],
                manufacturer=_el_text(game, "Developer") or "",
                genre=_el_text(game, "Genre") or "",
                players=_el_text(game, "MaxPlayers") or "",
                rating=_el_text(game, "CommunityStarRating") or "",
                rom_name=Path(_el_text(game, "ApplicationPath") or "").stem,
                rom_path=_el_text(game, "ApplicationPath") or "",
            ))
    except Exception as e:
        logger.error("Failed to import LaunchBox XML %s: %s", platform_xml_path, e)
    return entries


def import_batocera_gamelist(gamelist_xml_path: str, system_name: str = "") -> List[GameEntry]:
    """Import games from a Batocera/EmulationStation gamelist.xml."""
    if not system_name:
        system_name = Path(gamelist_xml_path).parent.name
    entries = []
    try:
        tree = ET.parse(gamelist_xml_path)
        root = tree.getroot()
        for game in root.findall(".//game"):
            name = _el_text(game, "name") or ""
            path = _el_text(game, "path") or ""
            if not name and path:
                name = Path(path).stem
            if not name:
                continue
            entries.append(GameEntry(
                name=name,
                system=system_name,
                source="Batocera gamelist.xml",
                year=(_el_text(game, "releasedate") or "")[:4],
                manufacturer=_el_text(game, "developer") or "",
                genre=_el_text(game, "genre") or "",
                players=_el_text(game, "players") or "",
                rating=_el_text(game, "rating") or "",
                rom_name=Path(path).stem if path else "",
                rom_path=path,
            ))
    except Exception as e:
        logger.error("Failed to import Batocera gamelist %s: %s", gamelist_xml_path, e)
    return entries


def import_csv(csv_path: str) -> List[GameEntry]:
    """Import games from M65 standardized CSV format."""
    entries = []
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(GameEntry(
                    name=row.get("name", ""),
                    system=row.get("system", ""),
                    source=row.get("source", "CSV import"),
                    year=row.get("year", ""),
                    manufacturer=row.get("manufacturer", ""),
                    genre=row.get("genre", ""),
                    players=row.get("players", ""),
                    rating=row.get("rating", ""),
                    rom_name=row.get("rom_name", ""),
                    rom_path=row.get("rom_path", ""),
                    file_size_mb=float(row.get("file_size_mb", 0) or 0),
                    variant=row.get("variant", ""),
                ))
    except Exception as e:
        logger.error("Failed to import CSV %s: %s", csv_path, e)
    return entries


# ---------------------------------------------------------------------------
# Export: Write List[GameEntry] -> various frontend formats
# ---------------------------------------------------------------------------

def export_hyperspin_xml(entries: List[GameEntry], output_path: str,
                         system_name: str = "") -> str:
    """Export games to HyperSpin XML database format."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    root = ET.Element("menu")
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "listname").text = system_name or "Exported"
    ET.SubElement(header, "lastlistupdate").text = ""
    ET.SubElement(header, "listversion").text = "1.0"
    ET.SubElement(header, "exporterversion").text = "KINHANK-Toolkit M58"

    for entry in entries:
        game = ET.SubElement(root, "game", name=entry.rom_name or entry.name)
        ET.SubElement(game, "description").text = entry.name
        if entry.year:
            ET.SubElement(game, "year").text = entry.year
        if entry.manufacturer:
            ET.SubElement(game, "manufacturer").text = entry.manufacturer
        if entry.genre:
            ET.SubElement(game, "genre").text = entry.genre
        if entry.players:
            ET.SubElement(game, "players").text = entry.players
        if entry.rating:
            ET.SubElement(game, "rating").text = entry.rating

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    # Remove extra XML declaration minidom adds
    lines = xml_str.split("\n")
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    xml_str = '<?xml version="1.0"?>\n' + "\n".join(lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    logger.info("Exported %d games to HyperSpin XML: %s", len(entries), output_path)
    return output_path


def export_attractmode_romlist(entries: List[GameEntry], output_path: str) -> str:
    """Export games to AttractMode romlist .txt format.

    Format: romname;title;emulator;cloneof;year;manufacturer;category;players;rotation;control;status;displaycount;displaytype;altromname;alttitle;extra;buttons
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("#Name;Title;Emulator;CloneOf;Year;Manufacturer;Category;Players;Rotation;Control;Status;DisplayCount;DisplayType;AltRomname;AltTitle;Extra;Buttons\n")
        for entry in entries:
            rom = entry.rom_name or _sanitize_romname(entry.name)
            line_parts = [
                rom,                    # romname
                entry.name,             # title
                entry.system,           # emulator
                "",                     # cloneof
                entry.year,             # year
                entry.manufacturer,     # manufacturer
                entry.genre,            # category
                entry.players,          # players
                "0",                    # rotation
                "",                     # control
                "",                     # status
                "",                     # displaycount
                "",                     # displaytype
                "",                     # altromname
                "",                     # alttitle
                "",                     # extra
                "",                     # buttons
            ]
            f.write(";".join(line_parts) + "\n")

    logger.info("Exported %d games to AttractMode romlist: %s", len(entries), output_path)
    return output_path


def export_launchbox_xml(entries: List[GameEntry], output_path: str,
                         platform: str = "") -> str:
    """Export games to LaunchBox Platform XML format."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    root = ET.Element("LaunchBox")
    for entry in entries:
        game = ET.SubElement(root, "Game")
        ET.SubElement(game, "Title").text = entry.name
        ET.SubElement(game, "Platform").text = platform or entry.system
        if entry.rom_path:
            ET.SubElement(game, "ApplicationPath").text = entry.rom_path
        elif entry.rom_name:
            ET.SubElement(game, "ApplicationPath").text = entry.rom_name
        if entry.year:
            ET.SubElement(game, "ReleaseDate").text = f"{entry.year}-01-01T00:00:00"
        if entry.manufacturer:
            ET.SubElement(game, "Developer").text = entry.manufacturer
        if entry.genre:
            ET.SubElement(game, "Genre").text = entry.genre
        if entry.players:
            ET.SubElement(game, "MaxPlayers").text = entry.players
        if entry.rating:
            ET.SubElement(game, "CommunityStarRating").text = entry.rating

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    logger.info("Exported %d games to LaunchBox XML: %s", len(entries), output_path)
    return output_path


def export_batocera_gamelist(entries: List[GameEntry], output_path: str) -> str:
    """Export games to Batocera/EmulationStation gamelist.xml format."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    root = ET.Element("gameList")
    for entry in entries:
        game = ET.SubElement(root, "game")
        path = entry.rom_path or f"./{entry.rom_name}" if entry.rom_name else f"./{_sanitize_romname(entry.name)}"
        ET.SubElement(game, "path").text = path
        ET.SubElement(game, "name").text = entry.name
        if entry.year:
            ET.SubElement(game, "releasedate").text = f"{entry.year}0101T000000"
        if entry.manufacturer:
            ET.SubElement(game, "developer").text = entry.manufacturer
        if entry.genre:
            ET.SubElement(game, "genre").text = entry.genre
        if entry.players:
            ET.SubElement(game, "players").text = entry.players
        if entry.rating:
            ET.SubElement(game, "rating").text = entry.rating

    xml_str = minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(indent="  ")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_str)
    logger.info("Exported %d games to Batocera gamelist: %s", len(entries), output_path)
    return output_path


def export_csv(entries: List[GameEntry], output_path: str) -> str:
    """Export games to M65 standardized CSV format."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fieldnames = [
        "name", "system", "source", "year", "manufacturer",
        "genre", "players", "rating", "rom_name", "rom_path",
        "file_size_mb", "variant"
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(asdict(entry))
    logger.info("Exported %d games to CSV: %s", len(entries), output_path)
    return output_path


# ---------------------------------------------------------------------------
# High-level conversion functions
# ---------------------------------------------------------------------------

FORMATS = {
    "hyperspin":    {"ext": ".xml", "import": import_hyperspin_xml, "export": export_hyperspin_xml},
    "attractmode":  {"ext": ".txt", "import": import_attractmode_romlist, "export": export_attractmode_romlist},
    "launchbox":    {"ext": ".xml", "import": import_launchbox_xml, "export": export_launchbox_xml},
    "batocera":     {"ext": ".xml", "import": import_batocera_gamelist, "export": export_batocera_gamelist},
    "csv":          {"ext": ".csv", "import": import_csv, "export": export_csv},
}


def convert(input_path: str, input_format: str,
            output_path: str, output_format: str,
            system_name: str = "") -> Dict:
    """
    Convert a game list between any two supported formats.

    Args:
        input_path: Path to source file
        input_format: One of: hyperspin, attractmode, launchbox, batocera, csv
        output_path: Path to write converted file
        output_format: Target format (same options as input_format)
        system_name: System name override (optional)

    Returns:
        Dict with conversion results
    """
    if input_format not in FORMATS:
        return {"error": f"Unknown input format: {input_format}. Use: {list(FORMATS.keys())}"}
    if output_format not in FORMATS:
        return {"error": f"Unknown output format: {output_format}. Use: {list(FORMATS.keys())}"}

    # Import
    importer = FORMATS[input_format]["import"]
    if input_format in ("hyperspin", "attractmode", "batocera"):
        entries = importer(input_path, system_name)
    else:
        entries = importer(input_path)

    if not entries:
        return {
            "error": f"No games found in {input_path} (format: {input_format})",
            "games": 0,
        }

    # Override system if specified
    if system_name:
        for e in entries:
            e.system = system_name

    # Export
    exporter = FORMATS[output_format]["export"]
    if output_format in ("hyperspin",):
        exporter(entries, output_path, system_name)
    elif output_format == "launchbox":
        exporter(entries, output_path, system_name)
    else:
        exporter(entries, output_path)

    return {
        "input": input_path,
        "input_format": input_format,
        "output": output_path,
        "output_format": output_format,
        "games": len(entries),
        "systems": len(set(e.system for e in entries)),
    }


def batch_convert(input_dir: str, input_format: str,
                  output_dir: str, output_format: str) -> Dict:
    """
    Convert all game list files in a directory from one format to another.

    Args:
        input_dir: Directory containing source files
        input_format: Source format
        output_dir: Directory to write converted files
        output_format: Target format
    """
    if input_format not in FORMATS or output_format not in FORMATS:
        return {"error": "Unknown format"}

    in_ext = FORMATS[input_format]["ext"]
    out_ext = FORMATS[output_format]["ext"]
    results = []
    total_games = 0

    for f in sorted(os.listdir(input_dir)):
        if not f.endswith(in_ext):
            continue
        stem = Path(f).stem
        in_path = os.path.join(input_dir, f)
        out_path = os.path.join(output_dir, stem + out_ext)

        result = convert(in_path, input_format, out_path, output_format, stem)
        results.append(result)
        total_games += result.get("games", 0)

    return {
        "files_converted": len([r for r in results if "error" not in r]),
        "total_games": total_games,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xtag(block: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.DOTALL)
    return m.group(1).strip() if m else None


def _el_text(parent: ET.Element, tag: str) -> Optional[str]:
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else None


def _sanitize_romname(name: str) -> str:
    """Convert a game title to a safe ROM filename."""
    name = re.sub(r'[^\w\s\-]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name.lower()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 5:
        print("Usage: python frontend_converter.py <input> <in_format> <output> <out_format> [system]")
        print("  Formats: hyperspin, attractmode, launchbox, batocera, csv")
        print("  Examples:")
        print("    python frontend_converter.py MAME.xml hyperspin MAME.txt attractmode MAME")
        print("    python frontend_converter.py romlist.txt attractmode gamelist.xml batocera")
        print("    python frontend_converter.py games.csv csv Platform.xml launchbox")
        sys.exit(1)

    in_path = sys.argv[1]
    in_fmt = sys.argv[2]
    out_path = sys.argv[3]
    out_fmt = sys.argv[4]
    sys_name = sys.argv[5] if len(sys.argv) > 5 else ""

    result = convert(in_path, in_fmt, out_path, out_fmt, sys_name)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)
    print(f"Converted {result['games']} games: {in_path} ({in_fmt}) -> {out_path} ({out_fmt})")
