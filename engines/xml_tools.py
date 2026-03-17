"""HyperSpin XML Database Tools — validate, merge, rebuild, and filter XML game databases.

Milestone M10: Provides pure-Python tooling for managing HyperSpin-format XML
database files without requiring external dependencies.

Functions:
  - validate_xml      — check structure, duplicates, missing fields, encoding
  - merge_xml         — merge two or more XML databases, dedup by game name
  - rebuild_xml       — rebuild an XML from a ROM directory + optional metadata source
  - filter_xml        — filter XML to only games present in a ROM directory
  - sort_xml          — sort games alphabetically within an XML
  - stats_xml         — return counts, year range, manufacturer stats
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit

log = get_logger("xml_tools")

# HyperSpin XML game fields
GAME_FIELDS = ("description", "cloneof", "crc", "manufacturer", "year",
               "genre", "rating", "enabled")

ROM_EXTENSIONS = {
    ".zip", ".7z", ".chd", ".iso", ".bin", ".cue", ".img", ".gcm",
    ".nds", ".gba", ".gb", ".gbc", ".nes", ".sfc", ".smc", ".gen",
    ".md", ".gg", ".sms", ".pce", ".ngp", ".ws", ".col", ".a26",
    ".a78", ".lnx", ".jag", ".n64", ".z64", ".v64", ".ndd",
    ".pbp", ".cso", ".rvz", ".wbfs", ".gcz", ".xci", ".nsp",
}


# ═══════════════════════════════════════════════════════════════════════
# Parsing helpers
# ═══════════════════════════════════════════════════════════════════════

def _parse_games(xml_path: Path) -> tuple[Optional[ET.ElementTree], list[ET.Element]]:
    """Parse an XML file and return (tree, list-of-game-elements)."""
    if not xml_path.exists():
        return None, []
    try:
        tree = ET.parse(str(xml_path))
        games = list(tree.getroot().iter("game"))
        return tree, games
    except ET.ParseError as exc:
        log.error("XML parse error in %s: %s", xml_path, exc)
        return None, []
    except Exception as exc:
        log.error("Failed to read %s: %s", xml_path, exc)
        return None, []


def _game_to_dict(el: ET.Element) -> dict[str, str]:
    """Convert a <game> element to a flat dict."""
    d: dict[str, str] = {"name": el.get("name", "")}
    for field in GAME_FIELDS:
        child = el.find(field)
        d[field] = child.text if child is not None and child.text else ""
    return d


def _dict_to_element(d: dict[str, str]) -> ET.Element:
    """Convert a flat dict back to a <game> element."""
    el = ET.Element("game", name=d.get("name", ""))
    for field in GAME_FIELDS:
        sub = ET.SubElement(el, field)
        sub.text = d.get(field, "")
    return el


def _write_xml(games: list[dict[str, str]], output_path: Path,
               list_name: str = "", indent: bool = True) -> dict[str, Any]:
    """Write a list of game dicts as a HyperSpin XML file."""
    root = ET.Element("menu")

    # Header
    header = ET.SubElement(root, "header")
    ET.SubElement(header, "listname").text = list_name or output_path.stem
    ET.SubElement(header, "lastlistupdate").text = datetime.now().strftime("%Y-%m-%d")
    ET.SubElement(header, "listversion").text = "1.0"
    ET.SubElement(header, "exporterversion").text = "HyperSpin Toolkit M10"

    for gd in games:
        root.append(_dict_to_element(gd))

    tree = ET.ElementTree(root)
    if indent:
        ET.indent(tree, space="  ")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(output_path), encoding="unicode", xml_declaration=True)

    return {"output_path": str(output_path), "game_count": len(games)}


# ═══════════════════════════════════════════════════════════════════════
# Validate
# ═══════════════════════════════════════════════════════════════════════

def validate_xml(xml_path: str | Path) -> dict[str, Any]:
    """Validate a HyperSpin XML database file.

    Checks:
      - Well-formed XML
      - Root element is <menu>
      - Each <game> has a name attribute
      - Duplicate game names
      - Missing recommended fields (description, year, manufacturer)
      - Empty games (no child elements)

    Returns:
        {valid, game_count, issues: [{severity, type, detail}], duplicates, ...}
    """
    xml_path = Path(xml_path)
    result: dict[str, Any] = {
        "path": str(xml_path),
        "valid": True,
        "game_count": 0,
        "issues": [],
        "duplicates": [],
        "missing_fields": {},
    }

    if not xml_path.exists():
        result["valid"] = False
        result["issues"].append({"severity": "error", "type": "not_found",
                                  "detail": f"File not found: {xml_path}"})
        return result

    # Parse
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError as exc:
        result["valid"] = False
        result["issues"].append({"severity": "error", "type": "parse_error",
                                  "detail": f"XML parse error: {exc}"})
        return result

    root = tree.getroot()

    # Check root tag
    if root.tag != "menu":
        result["issues"].append({"severity": "warn", "type": "wrong_root",
                                  "detail": f"Root element is <{root.tag}>, expected <menu>"})

    # Check header
    header = root.find("header")
    if header is None:
        result["issues"].append({"severity": "info", "type": "no_header",
                                  "detail": "No <header> element found"})

    # Validate games
    games = list(root.iter("game"))
    result["game_count"] = len(games)

    if not games:
        result["issues"].append({"severity": "warn", "type": "empty",
                                  "detail": "XML contains no <game> elements"})
        return result

    name_counts: Counter[str] = Counter()
    field_missing: dict[str, int] = defaultdict(int)

    for game_el in games:
        name = game_el.get("name", "")
        if not name:
            result["issues"].append({"severity": "error", "type": "no_name",
                                      "detail": "Found <game> without name attribute"})
            result["valid"] = False
            continue

        name_counts[name] += 1

        # Check recommended fields
        for field in ("description", "year", "manufacturer"):
            child = game_el.find(field)
            if child is None or not (child.text and child.text.strip()):
                field_missing[field] += 1

    # Duplicates
    dupes = {n: c for n, c in name_counts.items() if c > 1}
    if dupes:
        result["duplicates"] = [{"name": n, "count": c} for n, c in sorted(dupes.items())]
        result["issues"].append({
            "severity": "warn", "type": "duplicates",
            "detail": f"{len(dupes)} duplicate game names found",
        })

    # Missing fields summary
    result["missing_fields"] = dict(field_missing)
    for field, count in field_missing.items():
        if count > 0:
            result["issues"].append({
                "severity": "info", "type": "missing_field",
                "detail": f"{count} games missing <{field}>",
            })

    log.info("Validated %s: %d games, %d issues", xml_path.name,
             result["game_count"], len(result["issues"]))
    return result


# ═══════════════════════════════════════════════════════════════════════
# Merge
# ═══════════════════════════════════════════════════════════════════════

def merge_xml(
    xml_paths: list[str | Path],
    output_path: str | Path,
    *,
    dedup: bool = True,
    prefer_last: bool = True,
    sort: bool = True,
) -> dict[str, Any]:
    """Merge multiple HyperSpin XML databases into one.

    Args:
        xml_paths:    List of XML files to merge (order matters when prefer_last=True).
        output_path:  Where to write the merged XML.
        dedup:        Remove duplicate game names (default True).
        prefer_last:  When dedup, keep the entry from the later file (default True).
        sort:         Sort games alphabetically by name (default True).

    Returns:
        {output_path, total_input, merged_count, duplicates_removed, sources}
    """
    output_path = Path(output_path)
    all_games: dict[str, dict[str, str]] = {}
    sources: dict[str, int] = {}
    total_input = 0
    dupes_removed = 0

    for xp in xml_paths:
        xp = Path(xp)
        _, game_els = _parse_games(xp)
        sources[str(xp)] = len(game_els)
        total_input += len(game_els)

        for el in game_els:
            gd = _game_to_dict(el)
            name = gd["name"]
            if not name:
                continue
            if dedup:
                if name in all_games:
                    dupes_removed += 1
                    if not prefer_last:
                        continue
                all_games[name] = gd
            else:
                # Allow duplicates — use counter suffix
                key = name
                i = 1
                while key in all_games:
                    key = f"{name}__dup{i}"
                    i += 1
                all_games[key] = gd

    game_list = list(all_games.values())
    if sort:
        game_list.sort(key=lambda g: g.get("name", "").lower())

    write_result = _write_xml(game_list, output_path)

    result = {
        "output_path": str(output_path),
        "total_input": total_input,
        "merged_count": len(game_list),
        "duplicates_removed": dupes_removed,
        "sources": sources,
    }

    log.info("Merged %d XML files -> %s (%d games)", len(xml_paths),
             output_path.name, len(game_list))
    audit("xml_merge", str(output_path), result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Rebuild from ROM directory
# ═══════════════════════════════════════════════════════════════════════

def rebuild_xml(
    rom_dir: str | Path,
    output_path: str | Path,
    *,
    reference_xml: str | Path | None = None,
    system_name: str = "",
) -> dict[str, Any]:
    """Rebuild a HyperSpin XML database from a ROM directory.

    Creates a <game> entry for every ROM file found. If a reference XML is
    provided, metadata (description, year, manufacturer, genre) is pulled
    from it for matching game names.

    Args:
        rom_dir:        Directory containing ROM files.
        output_path:    Where to write the rebuilt XML.
        reference_xml:  Optional existing XML to pull metadata from.
        system_name:    System name for the header.

    Returns:
        {output_path, rom_count, with_metadata, without_metadata}
    """
    rom_dir = Path(rom_dir)
    output_path = Path(output_path)

    # Index reference metadata
    ref_map: dict[str, dict[str, str]] = {}
    if reference_xml:
        ref_path = Path(reference_xml)
        _, ref_games = _parse_games(ref_path)
        for el in ref_games:
            gd = _game_to_dict(el)
            if gd["name"]:
                ref_map[gd["name"]] = gd

    # Scan ROMs
    rom_names: list[str] = []
    if rom_dir.exists():
        for f in sorted(rom_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in ROM_EXTENSIONS:
                rom_names.append(f.stem)

    # Build game entries
    games: list[dict[str, str]] = []
    with_meta = 0
    without_meta = 0

    for name in rom_names:
        if name in ref_map:
            games.append(ref_map[name])
            with_meta += 1
        else:
            games.append({
                "name": name,
                "description": name,
                "year": "",
                "manufacturer": "",
                "genre": "",
                "rating": "",
                "cloneof": "",
                "crc": "",
                "enabled": "Yes",
            })
            without_meta += 1

    _write_xml(games, output_path, list_name=system_name or output_path.stem)

    result = {
        "output_path": str(output_path),
        "rom_count": len(rom_names),
        "with_metadata": with_meta,
        "without_metadata": without_meta,
    }

    log.info("Rebuilt XML %s: %d ROMs (%d with metadata)", output_path.name,
             len(rom_names), with_meta)
    audit("xml_rebuild", str(output_path), result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Filter XML to ROMs present
# ═══════════════════════════════════════════════════════════════════════

def filter_xml(
    xml_path: str | Path,
    rom_dir: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Filter a HyperSpin XML to only games that have ROMs present.

    Args:
        xml_path:    Source XML database.
        rom_dir:     ROM directory to check against.
        output_path: Where to write filtered XML (default: overwrite source).

    Returns:
        {output_path, original_count, filtered_count, removed_count}
    """
    xml_path = Path(xml_path)
    rom_dir = Path(rom_dir)
    output_path = Path(output_path) if output_path else xml_path

    _, game_els = _parse_games(xml_path)
    original_count = len(game_els)

    # Index ROM stems
    rom_stems: set[str] = set()
    if rom_dir.exists():
        for f in rom_dir.iterdir():
            if f.is_file() and f.suffix.lower() in ROM_EXTENSIONS:
                rom_stems.add(f.stem)

    # Filter
    kept: list[dict[str, str]] = []
    for el in game_els:
        gd = _game_to_dict(el)
        if gd["name"] in rom_stems:
            kept.append(gd)

    _write_xml(kept, output_path, list_name=output_path.stem)

    result = {
        "output_path": str(output_path),
        "original_count": original_count,
        "filtered_count": len(kept),
        "removed_count": original_count - len(kept),
    }

    log.info("Filtered %s: %d -> %d games", xml_path.name, original_count, len(kept))
    audit("xml_filter", str(output_path), result)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Sort
# ═══════════════════════════════════════════════════════════════════════

def sort_xml(
    xml_path: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Sort games in a HyperSpin XML alphabetically by name.

    Args:
        xml_path:    Source XML.
        output_path: Where to write sorted XML (default: overwrite source).

    Returns:
        {output_path, game_count}
    """
    xml_path = Path(xml_path)
    output_path = Path(output_path) if output_path else xml_path

    _, game_els = _parse_games(xml_path)
    games = [_game_to_dict(el) for el in game_els]
    games.sort(key=lambda g: g.get("name", "").lower())

    write_result = _write_xml(games, output_path, list_name=output_path.stem)

    log.info("Sorted %s: %d games", output_path.name, len(games))
    return write_result


# ═══════════════════════════════════════════════════════════════════════
# Statistics
# ═══════════════════════════════════════════════════════════════════════

def stats_xml(xml_path: str | Path) -> dict[str, Any]:
    """Return statistics for a HyperSpin XML database.

    Returns:
        {path, game_count, year_range, top_manufacturers, top_genres,
         field_completeness, has_header}
    """
    xml_path = Path(xml_path)
    result: dict[str, Any] = {"path": str(xml_path)}

    tree, game_els = _parse_games(xml_path)
    if tree is None:
        result["error"] = "Could not parse XML"
        return result

    root = tree.getroot()
    result["has_header"] = root.find("header") is not None
    result["game_count"] = len(game_els)

    years: list[str] = []
    manufacturers: Counter[str] = Counter()
    genres: Counter[str] = Counter()
    field_present: dict[str, int] = defaultdict(int)

    for el in game_els:
        for field in GAME_FIELDS:
            child = el.find(field)
            if child is not None and child.text and child.text.strip():
                field_present[field] += 1

        year_el = el.find("year")
        if year_el is not None and year_el.text and year_el.text.strip():
            years.append(year_el.text.strip())

        mfg_el = el.find("manufacturer")
        if mfg_el is not None and mfg_el.text and mfg_el.text.strip():
            manufacturers[mfg_el.text.strip()] += 1

        genre_el = el.find("genre")
        if genre_el is not None and genre_el.text and genre_el.text.strip():
            genres[genre_el.text.strip()] += 1

    # Year range
    numeric_years = [y for y in years if y.isdigit()]
    if numeric_years:
        result["year_range"] = {"min": min(numeric_years), "max": max(numeric_years)}
    else:
        result["year_range"] = None

    # Top manufacturers and genres
    result["top_manufacturers"] = [{"name": n, "count": c}
                                    for n, c in manufacturers.most_common(10)]
    result["top_genres"] = [{"name": n, "count": c}
                             for n, c in genres.most_common(10)]

    # Field completeness
    total = len(game_els) or 1
    result["field_completeness"] = {
        f: round(field_present.get(f, 0) / total * 100, 1) for f in GAME_FIELDS
    }

    return result
