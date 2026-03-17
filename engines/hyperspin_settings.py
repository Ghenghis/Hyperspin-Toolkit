"""M57 — HyperSpin Settings Manager & HyperHQ Bridge.

Reads, writes, and validates HyperSpin configuration files including:
  - HyperSpin.ini (main configuration)
  - Per-system Settings INI files (Settings/{System}.ini)
  - Wheel behavior, navigation, themes, startup/exit, attract mode
  - Path validation for referenced directories/files
  - Recommended settings presets (performance, quality, cabinet)

HyperSpin INI files use a Windows INI-like format with sections and
key=value pairs.  Some values are booleans (true/false), some numeric,
some paths.  This engine normalises reads and provides typed accessors.
"""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("hyperspin_settings")


# ═══════════════════════════════════════════════════════════════════════
# Constants — known HyperSpin INI sections and keys
# ═══════════════════════════════════════════════════════════════════════

# Main HyperSpin.ini sections and their known keys with defaults
MAIN_SECTIONS: dict[str, dict[str, str]] = {
    "Main": {
        "Menu_Mode": "multi",
        "Single_Mode_System": "",
        "Exit_Action": "exit",
        "Exit_Default": "yes",
        "Exit_Confirmation": "yes",
    },
    "Optimizer": {
        "CPU_Priority": "normal",
        "Threads": "auto",
    },
    "Resolution": {
        "FullScreen": "true",
        "Width": "0",
        "Height": "0",
    },
    "Navigation": {
        "Use_Last_Game": "true",
        "Last_System": "",
        "Last_Game": "",
        "Remove_Info_Text": "false",
        "Remove_Info_Wheel": "false",
    },
    "Keyboard": {
        "Key_Delay": "300",
        "Key_Repeat_Delay": "80",
        "Exit": "Escape",
        "Quit": "",
        "Up": "Up",
        "Down": "Down",
        "Left": "Left",
        "Right": "Right",
        "Select": "Return",
        "Back": "Back",
        "HyperSpin": "H",
        "Genre": "G",
        "Favorites": "F",
    },
    "Joystick": {
        "Enabled": "true",
        "Joy_Num": "0",
        "Joy_Up": "Joy1.Up",
        "Joy_Down": "Joy1.Down",
        "Joy_Left": "Joy1.Left",
        "Joy_Right": "Joy1.Right",
        "Joy_Select": "Joy1.Button1",
        "Joy_Back": "Joy1.Button2",
        "Joy_HyperSpin": "",
        "Joy_Genre": "",
        "Joy_Favorites": "",
    },
    "Trackball": {
        "Enabled": "false",
        "Sensitivity": "5",
    },
    "LEDBlinky": {
        "Active": "false",
        "Path": "",
    },
    "HyperPause": {
        "Enabled": "false",
    },
    "Sound": {
        "Master_Volume": "100",
        "Wheel_Click": "true",
        "Interface_Click": "true",
        "Video_Volume": "100",
    },
    "Startup": {
        "Intro_Video": "",
        "Skip_Intro": "false",
    },
    "Attract_Mode": {
        "Enabled": "false",
        "Wait": "30",
        "MaxWait": "120",
        "HyperSpin": "false",
    },
    "Screensaver": {
        "Enabled": "false",
        "Wait": "300",
        "Type": "blank",
    },
    "Wheel": {
        "Alpha": "0.5",
        "Speed": "medium",
        "Style": "normal",
        "Pin_Center_Wheel": "true",
        "Letter_Choose": "true",
        "Letter_Wheel": "false",
        "Small_Wheel_Count": "8",
        "Normal_Wheel_Count": "15",
    },
}

# Per-system INI known sections
SYSTEM_SECTIONS: dict[str, dict[str, str]] = {
    "exe": {
        "Path": "",
        "ROM_Path": "",
        "Parameters": "",
        "UseRocketLauncher": "true",
        "RocketLauncherPath": "",
        "SearchSubFolders": "false",
        "PC_Game": "false",
    },
    "Navigation": {
        "Use_Last_Game": "true",
        "Last_Game": "",
        "Remove_Info_Text": "false",
        "Remove_Info_Wheel": "false",
    },
    "Themes": {
        "Use_Parent_Themes": "true",
        "Default_Theme": "default",
        "Animate_Outline": "true",
        "Particles": "true",
    },
    "Wheel": {
        "Alpha": "",
        "Speed": "",
        "Style": "",
        "Small_Wheel_Count": "",
        "Normal_Wheel_Count": "",
    },
    "Video_Defaults": {
        "Path": "",
    },
    "Sounds": {
        "Game_Sounds": "true",
        "Wheel_Click": "true",
    },
    "Special": {
        "Artwork1": "true",
        "Artwork2": "true",
        "Artwork3": "true",
        "Artwork4": "true",
    },
}

# Settings presets
PRESETS: dict[str, dict[str, dict[str, str]]] = {
    "performance": {
        "Wheel": {"Alpha": "0.8", "Speed": "fast", "Small_Wheel_Count": "6"},
        "Resolution": {"FullScreen": "true"},
        "Optimizer": {"CPU_Priority": "high"},
        "Attract_Mode": {"Enabled": "false"},
        "Screensaver": {"Enabled": "false"},
    },
    "quality": {
        "Wheel": {"Alpha": "0.4", "Speed": "medium", "Small_Wheel_Count": "10"},
        "Resolution": {"FullScreen": "true"},
        "Sound": {"Master_Volume": "100", "Video_Volume": "80"},
        "Attract_Mode": {"Enabled": "true", "Wait": "30"},
    },
    "cabinet": {
        "Resolution": {"FullScreen": "true"},
        "Main": {"Exit_Action": "none", "Exit_Confirmation": "no"},
        "Joystick": {"Enabled": "true"},
        "Keyboard": {"Exit": ""},
        "Attract_Mode": {"Enabled": "true", "Wait": "20"},
        "Screensaver": {"Enabled": "true", "Wait": "120"},
        "Wheel": {"Speed": "medium", "Pin_Center_Wheel": "true"},
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Result dataclasses
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SettingsValidation:
    """Result of validating a HyperSpin settings file."""
    filepath: str = ""
    exists: bool = False
    sections_found: int = 0
    keys_found: int = 0
    issues: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    broken_paths: list[str] = field(default_factory=list)
    health_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "filepath": self.filepath,
            "exists": self.exists,
            "sections_found": self.sections_found,
            "keys_found": self.keys_found,
            "issues": self.issues,
            "warnings": self.warnings,
            "broken_paths": self.broken_paths,
            "health_score": self.health_score,
        }


@dataclass
class SettingsAuditReport:
    """Full settings audit across main + per-system INIs."""
    main_ini: SettingsValidation = field(default_factory=SettingsValidation)
    system_count: int = 0
    healthy_systems: int = 0
    systems_with_issues: int = 0
    systems: dict[str, SettingsValidation] = field(default_factory=dict)
    total_broken_paths: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "main_ini": self.main_ini.to_dict(),
            "system_count": self.system_count,
            "healthy_systems": self.healthy_systems,
            "systems_with_issues": self.systems_with_issues,
            "systems": {k: v.to_dict() for k, v in self.systems.items()},
            "total_broken_paths": self.total_broken_paths,
        }


# ═══════════════════════════════════════════════════════════════════════
# INI reading/writing
# ═══════════════════════════════════════════════════════════════════════

def _make_parser() -> configparser.ConfigParser:
    """Create a ConfigParser configured for HyperSpin INI files."""
    return configparser.ConfigParser(
        interpolation=None,
        strict=False,
        comment_prefixes=(";", "#"),
        inline_comment_prefixes=(";",),
    )


def read_ini(ini_path: Path) -> dict[str, dict[str, str]]:
    """Read a HyperSpin INI file into a nested dict.

    Returns: {section: {key: value, ...}, ...}
    """
    ini_path = Path(ini_path)
    result: dict[str, dict[str, str]] = {}

    if not ini_path.exists():
        log.warning("INI file not found: %s", ini_path)
        return result

    parser = _make_parser()
    try:
        parser.read(str(ini_path), encoding="utf-8-sig")
    except (configparser.Error, UnicodeDecodeError) as exc:
        log.error("Failed to parse INI %s: %s", ini_path, exc)
        return result

    for section in parser.sections():
        result[section] = dict(parser.items(section))

    return result


def write_ini(ini_path: Path, data: dict[str, dict[str, str]]) -> bool:
    """Write a nested dict to a HyperSpin INI file.

    Preserves section ordering from the dict.
    Returns True on success.
    """
    ini_path = Path(ini_path)
    parser = _make_parser()

    for section, keys in data.items():
        parser[section] = keys

    try:
        ini_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ini_path, "w", encoding="utf-8") as fh:
            parser.write(fh)
        log.info("Wrote settings to %s", ini_path)
        return True
    except OSError as exc:
        log.error("Failed to write INI %s: %s", ini_path, exc)
        return False


def get_setting(
    ini_path: Path,
    section: str,
    key: str,
    default: str = "",
) -> str:
    """Read a single setting value from a HyperSpin INI file."""
    data = read_ini(ini_path)
    return data.get(section, {}).get(key, default)


def set_setting(
    ini_path: Path,
    section: str,
    key: str,
    value: str,
) -> bool:
    """Write a single setting value to a HyperSpin INI file.

    Creates the section if it doesn't exist.
    """
    data = read_ini(ini_path)
    if section not in data:
        data[section] = {}
    data[section][key] = value
    return write_ini(ini_path, data)


# ═══════════════════════════════════════════════════════════════════════
# Typed accessors
# ═══════════════════════════════════════════════════════════════════════

def get_bool(ini_path: Path, section: str, key: str, default: bool = False) -> bool:
    """Read a boolean setting (true/false/yes/no/1/0)."""
    val = get_setting(ini_path, section, key, "").lower().strip()
    if val in ("true", "yes", "1"):
        return True
    if val in ("false", "no", "0"):
        return False
    return default


def get_int(ini_path: Path, section: str, key: str, default: int = 0) -> int:
    """Read an integer setting."""
    val = get_setting(ini_path, section, key, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def get_float(ini_path: Path, section: str, key: str, default: float = 0.0) -> float:
    """Read a float setting."""
    val = get_setting(ini_path, section, key, "")
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_main_ini(
    ini_path: Optional[str | Path] = None,
    hs_root: Optional[str | Path] = None,
) -> SettingsValidation:
    """Validate the main HyperSpin.ini file.

    Checks:
      - File exists and is parseable
      - Expected sections present
      - Known keys have valid values
      - Referenced paths exist on disk
    """
    if ini_path is None:
        hs = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
        ini_path = hs / "Settings" / "HyperSpin.ini"
    else:
        ini_path = Path(ini_path)

    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    val = SettingsValidation(filepath=str(ini_path))
    val.exists = ini_path.exists()

    if not val.exists:
        val.issues.append({"severity": "error", "msg": f"HyperSpin.ini not found: {ini_path}"})
        val.health_score = 0.0
        return val

    data = read_ini(ini_path)
    val.sections_found = len(data)
    val.keys_found = sum(len(v) for v in data.values())

    # Check expected sections
    for section in MAIN_SECTIONS:
        if section not in data:
            val.warnings.append({
                "severity": "info",
                "msg": f"Missing section [{section}] — using defaults",
            })

    # Validate specific settings
    _validate_resolution(data, val)
    _validate_wheel(data, val)
    _validate_sound(data, val)
    _validate_paths_in_data(data, hs_root, val)

    # Score
    error_count = len([i for i in val.issues if i.get("severity") == "error"])
    warn_count = len(val.warnings)
    val.health_score = max(0.0, 100.0 - error_count * 25 - warn_count * 5 - len(val.broken_paths) * 10)

    return val


def _validate_resolution(data: dict, val: SettingsValidation) -> None:
    """Validate resolution settings."""
    res = data.get("Resolution", {})
    width = res.get("width", res.get("Width", "0"))
    height = res.get("height", res.get("Height", "0"))
    try:
        w, h = int(width), int(height)
        if w > 0 and h > 0 and (w < 640 or h < 480):
            val.warnings.append({
                "severity": "warn",
                "msg": f"Very low resolution: {w}x{h}",
            })
    except ValueError:
        val.issues.append({
            "severity": "error",
            "msg": f"Invalid resolution values: Width={width}, Height={height}",
        })


def _validate_wheel(data: dict, val: SettingsValidation) -> None:
    """Validate wheel settings."""
    wheel = data.get("Wheel", data.get("wheel", {}))
    alpha = wheel.get("alpha", wheel.get("Alpha", ""))
    if alpha:
        try:
            a = float(alpha)
            if not (0.0 <= a <= 1.0):
                val.warnings.append({
                    "severity": "warn",
                    "msg": f"Wheel Alpha {a} outside normal range 0.0-1.0",
                })
        except ValueError:
            val.issues.append({
                "severity": "error",
                "msg": f"Invalid Wheel Alpha value: {alpha}",
            })

    speed = wheel.get("speed", wheel.get("Speed", "")).lower()
    if speed and speed not in ("slow", "medium", "fast", "fastest"):
        val.warnings.append({
            "severity": "warn",
            "msg": f"Unknown Wheel Speed: {speed} (expected: slow/medium/fast/fastest)",
        })


def _validate_sound(data: dict, val: SettingsValidation) -> None:
    """Validate sound settings."""
    sound = data.get("Sound", data.get("sound", {}))
    vol = sound.get("master_volume", sound.get("Master_Volume", ""))
    if vol:
        try:
            v = int(vol)
            if not (0 <= v <= 100):
                val.warnings.append({
                    "severity": "warn",
                    "msg": f"Master_Volume {v} outside 0-100 range",
                })
        except ValueError:
            val.issues.append({
                "severity": "error",
                "msg": f"Invalid Master_Volume: {vol}",
            })


def _validate_paths_in_data(
    data: dict, hs_root: Path, val: SettingsValidation
) -> None:
    """Check any path-like values to see if they exist on disk."""
    path_keys = {"path", "rom_path", "rocketlauncherpath", "intro_video"}
    for section, keys in data.items():
        for key, value in keys.items():
            if key.lower() in path_keys and value:
                # Resolve relative paths against hs_root
                p = Path(value)
                if not p.is_absolute():
                    p = hs_root / value
                if not p.exists() and value.strip():
                    val.broken_paths.append(f"[{section}] {key} = {value}")


def validate_system_ini(
    system: str,
    settings_dir: Optional[str | Path] = None,
    hs_root: Optional[str | Path] = None,
) -> SettingsValidation:
    """Validate a per-system INI file (Settings/{System}.ini)."""
    if settings_dir is None:
        hs = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
        settings_dir = hs / "Settings"
    else:
        settings_dir = Path(settings_dir)

    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    ini_path = settings_dir / f"{system}.ini"
    val = SettingsValidation(filepath=str(ini_path))
    val.exists = ini_path.exists()

    if not val.exists:
        val.issues.append({
            "severity": "warn",
            "msg": f"System settings not found: {ini_path}",
        })
        val.health_score = 50.0  # not fatal — defaults may work
        return val

    data = read_ini(ini_path)
    val.sections_found = len(data)
    val.keys_found = sum(len(v) for v in data.values())

    # Check exe section
    exe = data.get("exe", {})
    if not exe:
        val.warnings.append({
            "severity": "info",
            "msg": f"No [exe] section in {system}.ini",
        })

    # Validate paths
    _validate_paths_in_data(data, hs_root, val)

    # Check if UseRocketLauncher is set but path is missing
    use_rl = exe.get("userocketlauncher", exe.get("UseRocketLauncher", "")).lower()
    rl_path = exe.get("rocketlauncherpath", exe.get("RocketLauncherPath", ""))
    if use_rl in ("true", "1", "yes") and not rl_path:
        val.warnings.append({
            "severity": "warn",
            "msg": f"{system}: UseRocketLauncher=true but RocketLauncherPath is empty",
        })

    error_count = len([i for i in val.issues if i.get("severity") == "error"])
    warn_count = len(val.warnings)
    val.health_score = max(0.0, 100.0 - error_count * 25 - warn_count * 5 - len(val.broken_paths) * 10)

    return val


# ═══════════════════════════════════════════════════════════════════════
# Full audit
# ═══════════════════════════════════════════════════════════════════════

def audit_all_settings(
    hs_root: Optional[str | Path] = None,
) -> SettingsAuditReport:
    """Audit all HyperSpin settings: main INI + all per-system INIs.

    Args:
        hs_root: HyperSpin root directory.

    Returns:
        SettingsAuditReport with results for main + each system.
    """
    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    settings_dir = hs_root / "Settings"
    report = SettingsAuditReport()

    # Main INI
    main_ini = settings_dir / "HyperSpin.ini"
    report.main_ini = validate_main_ini(main_ini, hs_root)
    report.total_broken_paths += len(report.main_ini.broken_paths)

    # Per-system INIs
    if settings_dir.exists():
        for ini_file in sorted(settings_dir.glob("*.ini")):
            if ini_file.name.lower() == "hyperspin.ini":
                continue
            system = ini_file.stem
            sys_val = validate_system_ini(system, settings_dir, hs_root)
            report.systems[system] = sys_val
            report.total_broken_paths += len(sys_val.broken_paths)

            if sys_val.health_score >= 80:
                report.healthy_systems += 1
            else:
                report.systems_with_issues += 1

    report.system_count = len(report.systems)

    log.info(
        "Settings audit: main=%s, %d systems (%d healthy, %d with issues), %d broken paths",
        "OK" if report.main_ini.exists else "MISSING",
        report.system_count, report.healthy_systems,
        report.systems_with_issues, report.total_broken_paths,
    )

    return report


# ═══════════════════════════════════════════════════════════════════════
# Presets
# ═══════════════════════════════════════════════════════════════════════

def apply_preset(
    ini_path: Path,
    preset_name: str,
) -> bool:
    """Apply a settings preset to a HyperSpin.ini file.

    Available presets: "performance", "quality", "cabinet".
    Merges preset values into existing settings (doesn't overwrite
    keys not in the preset).

    Returns True on success.
    """
    ini_path = Path(ini_path)
    preset = PRESETS.get(preset_name)
    if preset is None:
        log.error("Unknown preset: %s (available: %s)", preset_name, list(PRESETS.keys()))
        return False

    data = read_ini(ini_path)

    for section, keys in preset.items():
        if section not in data:
            data[section] = {}
        for key, value in keys.items():
            data[section][key] = value

    success = write_ini(ini_path, data)
    if success:
        log.info("Applied preset '%s' to %s", preset_name, ini_path)
    return success


def list_presets() -> dict[str, dict[str, dict[str, str]]]:
    """Return all available settings presets."""
    return dict(PRESETS)


# ═══════════════════════════════════════════════════════════════════════
# System discovery
# ═══════════════════════════════════════════════════════════════════════

def list_configured_systems(
    hs_root: Optional[str | Path] = None,
) -> list[str]:
    """List all systems that have a Settings INI file."""
    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    settings_dir = hs_root / "Settings"
    if not settings_dir.exists():
        return []

    systems: list[str] = []
    for ini_file in sorted(settings_dir.glob("*.ini")):
        if ini_file.name.lower() != "hyperspin.ini":
            systems.append(ini_file.stem)
    return systems


def get_system_exe_config(
    system: str,
    hs_root: Optional[str | Path] = None,
) -> dict[str, str]:
    """Get the [exe] section for a system — emulator path, ROM path, params."""
    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    ini_path = hs_root / "Settings" / f"{system}.ini"
    data = read_ini(ini_path)
    return dict(data.get("exe", {}))
