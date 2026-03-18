"""M60 — RocketLauncher Keymapper, Statistics, MultiGame & 7z Manager.

Parses RocketLauncher statistics XML for play counts/time, manages
keymapper profiles (AHK/Xpadder/JoyToKey), validates MultiGame INI
settings, and checks 7z extraction configuration.

Directory layout expected:
    RocketLauncher/
      Data/
        Statistics/             ← Per-system XML play statistics
      Keymappers/
        {Keymapper}/            ← AHK, Xpadder, JoyToKey profiles
      Settings/
        {System}/               ← Per-system INI with [MultiGame], [7z] sections
        Global RocketLauncher.ini  ← 7z extraction settings
"""
from __future__ import annotations

import configparser
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("rl_stats_keymapper")

SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


# ── Data Classes ─────────────────────────────────────────────────────

@dataclass
class GamePlayStats:
    """Play statistics for a single game."""
    system: str
    game: str
    play_count: int = 0
    total_time_seconds: int = 0
    last_played: str = ""
    average_session_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "game": self.game,
            "play_count": self.play_count,
            "total_time_seconds": self.total_time_seconds,
            "total_time_display": _format_duration(self.total_time_seconds),
            "last_played": self.last_played,
            "average_session_seconds": self.average_session_seconds,
            "average_session_display": _format_duration(self.average_session_seconds),
        }


@dataclass
class SystemPlayStats:
    """Aggregated play stats for a system."""
    system: str
    total_games_played: int = 0
    total_play_count: int = 0
    total_time_seconds: int = 0
    most_played_game: str = ""
    most_played_count: int = 0
    last_played_game: str = ""
    last_played_date: str = ""
    games: list[GamePlayStats] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "total_games_played": self.total_games_played,
            "total_play_count": self.total_play_count,
            "total_time_seconds": self.total_time_seconds,
            "total_time_display": _format_duration(self.total_time_seconds),
            "most_played_game": self.most_played_game,
            "most_played_count": self.most_played_count,
            "last_played_game": self.last_played_game,
            "last_played_date": self.last_played_date,
            "games": [g.to_dict() for g in self.games],
        }


@dataclass
class KeymapperProfile:
    """A keymapper profile (AHK, Xpadder, JoyToKey)."""
    keymapper_type: str    # AHK, Xpadder, JoyToKey
    name: str
    path: str
    system: str = ""
    emulator: str = ""
    file_ext: str = ""
    file_size: int = 0
    has_buttons_mapped: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "keymapper_type": self.keymapper_type,
            "name": self.name,
            "path": self.path,
            "system": self.system,
            "emulator": self.emulator,
            "file_ext": self.file_ext,
            "file_size": self.file_size,
            "has_buttons_mapped": self.has_buttons_mapped,
        }


@dataclass
class MultiGameConfig:
    """MultiGame configuration for a system."""
    system: str
    enabled: bool = False
    multi_disc_games: list[str] = field(default_factory=list)
    ini_path: str = ""
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "enabled": self.enabled,
            "multi_disc_count": len(self.multi_disc_games),
            "multi_disc_games": self.multi_disc_games[:50],
            "ini_path": self.ini_path,
            "issues": self.issues,
        }


@dataclass
class SevenZipConfig:
    """7z extraction configuration."""
    enabled: bool = False
    extract_path: str = ""
    extract_path_exists: bool = False
    delete_temp_on_exit: bool = True
    cache_size_mb: int = 0
    current_cache_size_mb: float = 0.0
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "extract_path": self.extract_path,
            "extract_path_exists": self.extract_path_exists,
            "delete_temp_on_exit": self.delete_temp_on_exit,
            "cache_size_mb": self.cache_size_mb,
            "current_cache_size_mb": round(self.current_cache_size_mb, 1),
            "issues": self.issues,
        }


# ── Helpers ──────────────────────────────────────────────────────────

def _format_duration(seconds: int) -> str:
    """Format seconds as human-readable duration."""
    if seconds <= 0:
        return "0s"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    if s > 0 or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


def _safe_read_ini(ini_path: Path) -> Optional[configparser.ConfigParser]:
    """Safely read an INI file with fallback encoding."""
    parser = configparser.ConfigParser(strict=False)
    try:
        parser.read(str(ini_path), encoding="utf-8-sig")
        return parser
    except Exception:
        try:
            parser.read(str(ini_path), encoding="latin-1")
            return parser
        except Exception:
            return None


def _get_rl_root(rl_root: Optional[str] = None) -> Path:
    """Resolve RocketLauncher root from arg or config."""
    root_str = rl_root or cfg_get("paths.rocketlauncher_root", "")
    return Path(root_str)


def _dir_size_mb(path: Path) -> float:
    """Get total size of a directory in MB."""
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
    except Exception:
        pass
    return total / (1024 * 1024)


# ── Statistics Parser ────────────────────────────────────────────────

def parse_system_stats(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Parse play statistics for a single system from RL Statistics XML.

    RocketLauncher stores stats in:
        Data/Statistics/{System}.xml or Statistics/{System}.xml

    XML format (typical):
        <statistics>
          <game name="GameName">
            <stat name="Number_of_Times_Played" value="5" />
            <stat name="Total_Time_Played" value="3600" />
            <stat name="Last_Time_Played" value="20240101120000" />
          </game>
        </statistics>

    Returns:
        Dict with parsed game stats, aggregates, and leaderboard.
    """
    root = _get_rl_root(rl_root)
    stats = SystemPlayStats(system=system)

    # Try multiple possible locations
    possible_paths = [
        root / "Data" / "Statistics" / f"{system}.xml",
        root / "Statistics" / f"{system}.xml",
        root / "Data" / "Statistics" / system / "Statistics.xml",
    ]

    xml_path = None
    for p in possible_paths:
        if p.exists():
            xml_path = p
            break

    if xml_path is None:
        return {
            "system": system,
            "exists": False,
            "note": "No statistics file found",
            "searched": [str(p) for p in possible_paths],
            "stats": stats.to_dict(),
        }

    # Parse XML
    try:
        tree = ET.parse(str(xml_path))
        xml_root = tree.getroot()
    except ET.ParseError as e:
        return {
            "system": system,
            "exists": True,
            "xml_path": str(xml_path),
            "error": f"XML parse error: {e}",
            "stats": stats.to_dict(),
        }

    # Extract game stats
    for game_elem in xml_root.iter("game"):
        game_name = game_elem.get("name", "")
        if not game_name:
            continue

        gs = GamePlayStats(system=system, game=game_name)

        for stat_elem in game_elem.iter("stat"):
            stat_name = stat_elem.get("name", "").lower()
            stat_value = stat_elem.get("value", "0")

            if "times_played" in stat_name or "number_of_times" in stat_name:
                gs.play_count = _safe_int(stat_value)
            elif "total_time" in stat_name:
                gs.total_time_seconds = _safe_int(stat_value)
            elif "last_time" in stat_name:
                gs.last_played = _parse_rl_datetime(stat_value)

        if gs.play_count > 0:
            gs.average_session_seconds = gs.total_time_seconds // gs.play_count

        stats.games.append(gs)
        stats.total_play_count += gs.play_count
        stats.total_time_seconds += gs.total_time_seconds

        if gs.play_count > stats.most_played_count:
            stats.most_played_count = gs.play_count
            stats.most_played_game = game_name

        if gs.last_played > stats.last_played_date:
            stats.last_played_date = gs.last_played
            stats.last_played_game = game_name

    stats.total_games_played = len([g for g in stats.games if g.play_count > 0])

    # Sort by play count descending
    stats.games.sort(key=lambda g: g.play_count, reverse=True)

    return {
        "system": system,
        "exists": True,
        "xml_path": str(xml_path),
        "stats": stats.to_dict(),
    }


def _safe_int(value: str) -> int:
    """Safely parse int from string."""
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return 0


def _parse_rl_datetime(value: str) -> str:
    """Parse RocketLauncher datetime format (YYYYMMDDHHmmss) to ISO string."""
    value = value.strip()
    if len(value) >= 14 and value.isdigit():
        try:
            dt = datetime(
                int(value[:4]), int(value[4:6]), int(value[6:8]),
                int(value[8:10]), int(value[10:12]), int(value[12:14]),
            )
            return dt.isoformat()
        except (ValueError, IndexError):
            pass
    return value


# ── Most Played / Leaderboard ────────────────────────────────────────

def most_played(
    rl_root: Optional[str] = None,
    top_n: int = 25,
    systems: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Get the most-played games across all or specified systems.

    Returns:
        Dict with leaderboard, per-system totals, and play time analysis.
    """
    root = _get_rl_root(rl_root)
    all_games: list[GamePlayStats] = []
    system_totals: list[dict[str, Any]] = []

    # Discover stats files
    if systems is None:
        stats_dirs = [root / "Data" / "Statistics", root / "Statistics"]
        system_names: set[str] = set()
        for sd in stats_dirs:
            if sd.exists():
                for f in sd.iterdir():
                    if f.suffix.lower() == ".xml" and f.is_file():
                        system_names.add(f.stem)
        systems = sorted(system_names)

    for sys_name in systems:
        result = parse_system_stats(sys_name, str(root))
        sys_stats = result.get("stats", {})
        games = sys_stats.get("games", [])

        for g in games:
            gs = GamePlayStats(
                system=sys_name,
                game=g.get("game", ""),
                play_count=g.get("play_count", 0),
                total_time_seconds=g.get("total_time_seconds", 0),
                last_played=g.get("last_played", ""),
            )
            if gs.play_count > 0:
                all_games.append(gs)

        system_totals.append({
            "system": sys_name,
            "games_played": sys_stats.get("total_games_played", 0),
            "total_plays": sys_stats.get("total_play_count", 0),
            "total_time": sys_stats.get("total_time_display", "0s"),
            "total_time_seconds": sys_stats.get("total_time_seconds", 0),
        })

    # Sort by play count
    all_games.sort(key=lambda g: g.play_count, reverse=True)
    leaderboard = [g.to_dict() for g in all_games[:top_n]]

    # Sort by play time
    by_time = sorted(all_games, key=lambda g: g.total_time_seconds, reverse=True)
    time_leaderboard = [g.to_dict() for g in by_time[:top_n]]

    # System totals sorted by play count
    system_totals.sort(key=lambda s: s["total_plays"], reverse=True)

    total_plays = sum(g.play_count for g in all_games)
    total_time = sum(g.total_time_seconds for g in all_games)

    return {
        "total_unique_games": len(all_games),
        "total_plays": total_plays,
        "total_time_display": _format_duration(total_time),
        "systems_with_stats": len(systems),
        "most_played_by_count": leaderboard,
        "most_played_by_time": time_leaderboard,
        "system_totals": system_totals,
    }


# ── Keymapper Scanner ────────────────────────────────────────────────

KEYMAPPER_TYPES = {
    "AutoHotkey": {"exts": {".ahk"}, "dir_pattern": "autohotkey"},
    "Xpadder":    {"exts": {".xpadderprofile", ".xpaddercontroller"}, "dir_pattern": "xpadder"},
    "JoyToKey":   {"exts": {".cfg", ".ini"}, "dir_pattern": "joytokey"},
}


def scan_keymappers(
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Scan all keymapper profiles in RocketLauncher.

    Looks in: RocketLauncher/Keymappers/{Type}/

    Returns:
        Dict with profiles per keymapper type, coverage, and issues.
    """
    root = _get_rl_root(rl_root)
    km_root = root / "Keymappers"
    issues: list[dict[str, str]] = []
    profiles: list[KeymapperProfile] = []

    if not km_root.exists():
        return {
            "keymappers_dir": str(km_root),
            "exists": False,
            "profiles": [],
            "issues": [{"severity": SEVERITY_INFO, "message": "No Keymappers directory found"}],
        }

    type_counts: dict[str, int] = {}

    for km_dir in sorted(km_root.iterdir()):
        if not km_dir.is_dir():
            continue

        # Detect keymapper type from directory name
        km_type = _detect_keymapper_type(km_dir.name)
        type_counts[km_type] = type_counts.get(km_type, 0)

        # Scan for profiles
        for profile_file in km_dir.rglob("*"):
            if not profile_file.is_file():
                continue

            ext = profile_file.suffix.lower()
            if ext in (".txt", ".md", ".log"):
                continue

            size = profile_file.stat().st_size
            rel = profile_file.relative_to(km_dir)

            # Try to detect system/emulator from path
            system = ""
            emulator = ""
            if len(rel.parts) > 1:
                system = rel.parts[0]
            if len(rel.parts) > 2:
                emulator = rel.parts[1]

            prof = KeymapperProfile(
                keymapper_type=km_type,
                name=profile_file.stem,
                path=str(profile_file),
                system=system,
                emulator=emulator,
                file_ext=ext,
                file_size=size,
            )

            # Check if AHK script has button mappings
            if ext == ".ahk":
                prof.has_buttons_mapped = _ahk_has_mappings(profile_file)
                if not prof.has_buttons_mapped:
                    issues.append({
                        "severity": SEVERITY_WARN,
                        "message": f"AHK script may have no button mappings: {profile_file.name}",
                        "file": str(profile_file),
                    })

            profiles.append(prof)
            type_counts[km_type] = type_counts.get(km_type, 0) + 1

    return {
        "keymappers_dir": str(km_root),
        "exists": True,
        "total_profiles": len(profiles),
        "type_counts": type_counts,
        "profiles": [p.to_dict() for p in profiles[:200]],
        "issues": issues,
    }


def _detect_keymapper_type(dir_name: str) -> str:
    """Detect keymapper type from directory name."""
    name_lower = dir_name.lower()
    for km_type, info in KEYMAPPER_TYPES.items():
        if info["dir_pattern"] in name_lower:
            return km_type
    return dir_name


def _ahk_has_mappings(ahk_path: Path) -> bool:
    """Check if an AHK script contains button mapping hotkeys."""
    try:
        content = ahk_path.read_text(encoding="utf-8-sig", errors="ignore")
        # AHK hotkey patterns: Joy1::, ^a::, LButton::, etc.
        return bool(re.search(r"(?:Joy\d+|[A-Za-z]+Button|[A-Za-z]+::|Hotkey,)", content))
    except Exception:
        return True  # Assume valid if can't read


# ── MultiGame Validator ──────────────────────────────────────────────

def validate_multigame(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Validate MultiGame settings for a system.

    Checks the system INI for [MultiGame] section, validates that
    multi-disc configurations reference existing files.

    Common multi-disc systems: PS1, Saturn, Sega CD, PC Engine CD.
    """
    root = _get_rl_root(rl_root)
    config = MultiGameConfig(system=system)

    sys_ini = root / "Settings" / system / f"{system}.ini"
    config.ini_path = str(sys_ini)

    if not sys_ini.exists():
        config.issues.append({
            "severity": SEVERITY_INFO,
            "message": f"No system INI found: {sys_ini}",
        })
        return config.to_dict()

    parser = _safe_read_ini(sys_ini)
    if not parser:
        config.issues.append({
            "severity": SEVERITY_WARN,
            "message": f"Cannot parse INI: {sys_ini}",
        })
        return config.to_dict()

    # Check for MultiGame section
    mg_section = None
    for section in parser.sections():
        if section.lower() == "multigame":
            mg_section = section
            break

    if not mg_section:
        config.issues.append({
            "severity": SEVERITY_INFO,
            "message": f"No [MultiGame] section in {system}.ini",
        })
        return config.to_dict()

    config.enabled = True

    # Scan for multi-disc entries
    for key, value in parser.items(mg_section):
        if value.strip():
            config.multi_disc_games.append(f"{key}={value}")

    # Validate ROM paths in multi-disc entries
    rom_path = ""
    for section in parser.sections():
        for opt in ("rompath", "rom_path", "roms_path"):
            if parser.has_option(section, opt):
                rom_path = parser.get(section, opt).strip().strip('"')
                break
        if rom_path:
            break

    if rom_path and os.path.isdir(rom_path):
        for entry in config.multi_disc_games:
            parts = entry.split("=", 1)
            if len(parts) == 2:
                disc_files = [f.strip() for f in parts[1].split("|")]
                for df in disc_files:
                    if df and not (Path(rom_path) / df).exists():
                        config.issues.append({
                            "severity": SEVERITY_WARN,
                            "message": f"Multi-disc file not found: {df}",
                        })

    return config.to_dict()


# ── 7z Extraction Settings ───────────────────────────────────────────

def check_7z_settings(
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Validate 7z extraction settings in RocketLauncher global config.

    Checks extract path, temp dir, cache size, and cleanup policies.
    """
    root = _get_rl_root(rl_root)
    config = SevenZipConfig()

    # Check global RL INI for 7z settings
    global_ini = root / "Settings" / "Global RocketLauncher.ini"
    if not global_ini.exists():
        # Try alternate locations
        for alt in ["RocketLauncher.ini", "Settings/RocketLauncher.ini"]:
            alt_path = root / alt
            if alt_path.exists():
                global_ini = alt_path
                break

    if not global_ini.exists():
        config.issues.append({
            "severity": SEVERITY_INFO,
            "message": "Global RocketLauncher INI not found",
        })
        return config.to_dict()

    parser = _safe_read_ini(global_ini)
    if not parser:
        config.issues.append({
            "severity": SEVERITY_WARN,
            "message": "Cannot parse global RocketLauncher INI",
        })
        return config.to_dict()

    # Look for 7z related settings
    for section in parser.sections():
        section_lower = section.lower()
        if "7z" in section_lower or "extract" in section_lower or "archive" in section_lower:
            for key, value in parser.items(section):
                key_lower = key.lower()
                if "enable" in key_lower:
                    config.enabled = value.lower() in ("true", "1", "yes")
                elif "path" in key_lower or "dir" in key_lower:
                    config.extract_path = value.strip().strip('"')
                elif "delete" in key_lower or "clean" in key_lower:
                    config.delete_temp_on_exit = value.lower() in ("true", "1", "yes")
                elif "size" in key_lower or "limit" in key_lower:
                    config.cache_size_mb = _safe_int(value)

    # Validate extract path
    if config.extract_path:
        ep = Path(config.extract_path)
        config.extract_path_exists = ep.exists()
        if not config.extract_path_exists:
            config.issues.append({
                "severity": SEVERITY_WARN,
                "message": f"7z extract path does not exist: {config.extract_path}",
                "suggestion": f"Create directory: {config.extract_path}",
            })
        else:
            config.current_cache_size_mb = _dir_size_mb(ep)
            if config.cache_size_mb > 0 and config.current_cache_size_mb > config.cache_size_mb:
                config.issues.append({
                    "severity": SEVERITY_WARN,
                    "message": (f"7z cache exceeds limit: "
                                f"{config.current_cache_size_mb:.0f}MB > {config.cache_size_mb}MB"),
                    "suggestion": "Clear cache or increase limit",
                })
    elif config.enabled:
        config.issues.append({
            "severity": SEVERITY_WARN,
            "message": "7z extraction enabled but no extract path configured",
        })

    return config.to_dict()


# ── Full Integration Report ──────────────────────────────────────────

def rl_integration_report(
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Generate a comprehensive RocketLauncher integration report.

    Combines statistics, keymapper, multigame, and 7z checks into
    a single summary for the GUI dashboard.
    """
    root = _get_rl_root(rl_root)
    result: dict[str, Any] = {"rl_root": str(root)}

    if not root.exists():
        result["error"] = f"RocketLauncher root not found: {root}"
        return result

    # Play statistics overview
    stats = most_played(str(root), top_n=10)
    result["play_stats"] = {
        "total_unique_games": stats.get("total_unique_games", 0),
        "total_plays": stats.get("total_plays", 0),
        "total_time": stats.get("total_time_display", "0s"),
        "systems_with_stats": stats.get("systems_with_stats", 0),
        "top_5_by_count": stats.get("most_played_by_count", [])[:5],
        "system_totals": stats.get("system_totals", [])[:10],
    }

    # Keymapper overview
    km = scan_keymappers(str(root))
    result["keymappers"] = {
        "exists": km.get("exists", False),
        "total_profiles": km.get("total_profiles", 0),
        "type_counts": km.get("type_counts", {}),
        "issue_count": len(km.get("issues", [])),
    }

    # 7z settings
    result["seven_zip"] = check_7z_settings(str(root))

    # Count total issues
    total_issues = (
        len(km.get("issues", [])) +
        len(result["seven_zip"].get("issues", []))
    )
    result["total_issues"] = total_issues

    log.info(
        "RL integration report: %d games played, %d keymapper profiles, %d issues",
        stats.get("total_unique_games", 0),
        km.get("total_profiles", 0),
        total_issues,
    )

    return result
