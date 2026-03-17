"""M9 — RocketLauncher Config Validator.

Parses and validates all RocketLauncher .ini files, module directories,
system-to-emulator mappings, plugin configs, and path references.
Produces a structured report with severity-tagged issues and a health score.
"""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("rl_config_validator")

# Severity levels for issues
SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


@dataclass
class RLIssue:
    """A single validation issue."""
    severity: str
    category: str
    message: str
    file: str = ""
    section: str = ""
    key: str = ""

    def to_dict(self) -> dict[str, str]:
        d = {"severity": self.severity, "category": self.category, "message": self.message}
        if self.file:
            d["file"] = self.file
        if self.section:
            d["section"] = self.section
        if self.key:
            d["key"] = self.key
        return d


@dataclass
class ModuleInfo:
    """Information about a RocketLauncher module."""
    name: str
    path: str
    has_ahk: bool = False
    ahk_file: str = ""
    has_ini: bool = False
    dll_count: int = 0
    issues: list[RLIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "has_ahk": self.has_ahk,
            "ahk_file": self.ahk_file,
            "has_ini": self.has_ini,
            "dll_count": self.dll_count,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class SystemMapping:
    """A system-to-emulator mapping from RL settings."""
    system_name: str
    ini_path: str
    emulator_name: str = ""
    emulator_path: str = ""
    rom_path: str = ""
    default_module: str = ""
    has_ini: bool = True
    path_issues: list[RLIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_name": self.system_name,
            "ini_path": self.ini_path,
            "emulator_name": self.emulator_name,
            "emulator_path": self.emulator_path,
            "rom_path": self.rom_path,
            "default_module": self.default_module,
            "has_ini": self.has_ini,
            "path_issues": [i.to_dict() for i in self.path_issues],
        }


@dataclass
class RLValidationReport:
    """Full RocketLauncher validation report."""
    rl_root: str
    rl_exists: bool = False
    exe_exists: bool = False
    exe_path: str = ""
    global_ini_valid: bool = False
    module_count: int = 0
    system_count: int = 0
    plugin_count: int = 0
    settings_file_count: int = 0
    health_score: float = 0.0
    modules: list[ModuleInfo] = field(default_factory=list)
    system_mappings: list[SystemMapping] = field(default_factory=list)
    plugins: list[dict[str, Any]] = field(default_factory=list)
    issues: list[RLIssue] = field(default_factory=list)
    global_settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rl_root": self.rl_root,
            "rl_exists": self.rl_exists,
            "exe_exists": self.exe_exists,
            "exe_path": self.exe_path,
            "global_ini_valid": self.global_ini_valid,
            "module_count": self.module_count,
            "system_count": self.system_count,
            "plugin_count": self.plugin_count,
            "settings_file_count": self.settings_file_count,
            "health_score": self.health_score,
            "modules": [m.to_dict() for m in self.modules],
            "system_mappings": [s.to_dict() for s in self.system_mappings],
            "plugins": self.plugins,
            "issues": [i.to_dict() for i in self.issues],
            "global_settings": self.global_settings,
            "summary": {
                "total_issues": len(self.issues),
                "errors": sum(1 for i in self.issues if i.severity == SEVERITY_ERROR),
                "warnings": sum(1 for i in self.issues if i.severity == SEVERITY_WARN),
                "info": sum(1 for i in self.issues if i.severity == SEVERITY_INFO),
            },
        }


# ── Internal helpers ────────────────────────────────────────────────

def _safe_read_ini(ini_path: Path) -> configparser.ConfigParser | None:
    """Safely read an INI file, returning None on failure."""
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


def _check_path_value(value: str) -> tuple[bool, str]:
    """Check if a value looks like a path and whether it exists.

    Returns (is_path, resolved_path_or_empty).
    """
    value = value.strip().strip('"').strip("'")
    # Skip empty, URLs, relative, or short values
    if not value or len(value) < 4:
        return False, ""
    if value.startswith(("http://", "https://", "ftp://")):
        return False, ""
    # Windows absolute path pattern
    if re.match(r"^[A-Za-z]:\\", value):
        clean = value.split("|")[0].split(";")[0].strip()
        return True, clean
    return False, ""


def _validate_paths_in_ini(
    ini_path: Path,
    parser: configparser.ConfigParser,
    category: str = "config",
) -> list[RLIssue]:
    """Scan all values in an INI for broken path references."""
    issues: list[RLIssue] = []
    for section in parser.sections():
        for key, val in parser.items(section):
            is_path, clean = _check_path_value(val)
            if is_path and not os.path.exists(clean):
                issues.append(RLIssue(
                    severity=SEVERITY_WARN,
                    category=category,
                    message=f"Path does not exist: {clean}",
                    file=str(ini_path),
                    section=section,
                    key=key,
                ))
    return issues


# ── Validation functions ────────────────────────────────────────────

def validate_modules(rl_root: Path) -> tuple[list[ModuleInfo], list[RLIssue]]:
    """Validate all RocketLauncher module directories."""
    modules_dir = rl_root / "Modules"
    modules: list[ModuleInfo] = []
    issues: list[RLIssue] = []

    if not modules_dir.exists():
        issues.append(RLIssue(
            severity=SEVERITY_ERROR,
            category="modules",
            message="Modules directory not found",
            file=str(modules_dir),
        ))
        return modules, issues

    for d in sorted(modules_dir.iterdir()):
        if not d.is_dir():
            continue
        mod = ModuleInfo(name=d.name, path=str(d))

        # Check for .ahk script (the module launcher)
        ahk_files = list(d.glob("*.ahk"))
        if ahk_files:
            mod.has_ahk = True
            mod.ahk_file = ahk_files[0].name
        else:
            mod.issues.append(RLIssue(
                severity=SEVERITY_WARN,
                category="modules",
                message=f"Module '{d.name}' has no .ahk script",
                file=str(d),
            ))

        # Check for .ini settings
        ini_files = list(d.glob("*.ini"))
        mod.has_ini = bool(ini_files)

        # Count DLLs
        mod.dll_count = len(list(d.glob("*.dll")))

        modules.append(mod)
        issues.extend(mod.issues)

    return modules, issues


def validate_system_settings(
    rl_root: Path,
    module_names: set[str] | None = None,
) -> tuple[list[SystemMapping], list[RLIssue]]:
    """Validate per-system settings INI files."""
    settings_dir = rl_root / "Settings"
    mappings: list[SystemMapping] = []
    issues: list[RLIssue] = []

    if not settings_dir.exists():
        issues.append(RLIssue(
            severity=SEVERITY_ERROR,
            category="settings",
            message="Settings directory not found",
            file=str(settings_dir),
        ))
        return mappings, issues

    # Per-system settings directories
    for sys_dir in sorted(settings_dir.iterdir()):
        if not sys_dir.is_dir():
            continue
        # Skip known non-system dirs
        if sys_dir.name.lower() in ("global", "rocketlauncher", "_default"):
            continue

        sys_ini = sys_dir / f"{sys_dir.name}.ini"
        mapping = SystemMapping(
            system_name=sys_dir.name,
            ini_path=str(sys_ini),
            has_ini=sys_ini.exists(),
        )

        if not sys_ini.exists():
            # Check for any .ini in the folder
            alt_inis = list(sys_dir.glob("*.ini"))
            if alt_inis:
                sys_ini = alt_inis[0]
                mapping.ini_path = str(sys_ini)
                mapping.has_ini = True
            else:
                issues.append(RLIssue(
                    severity=SEVERITY_INFO,
                    category="settings",
                    message=f"No INI file for system '{sys_dir.name}'",
                    file=str(sys_dir),
                ))
                mappings.append(mapping)
                continue

        parser = _safe_read_ini(sys_ini)
        if not parser:
            issues.append(RLIssue(
                severity=SEVERITY_WARN,
                category="settings",
                message=f"Cannot parse INI for system '{sys_dir.name}'",
                file=str(sys_ini),
            ))
            mappings.append(mapping)
            continue

        # Extract key settings
        for section in parser.sections():
            section_lower = section.lower()
            for key, val in parser.items(section):
                key_lower = key.lower()
                if key_lower in ("emulator", "default_emulator"):
                    mapping.emulator_name = val
                elif key_lower in ("emulatorpath", "emulator_path"):
                    mapping.emulator_path = val
                elif key_lower in ("rompath", "rom_path", "romdir"):
                    mapping.rom_path = val
                elif key_lower in ("module", "default_module"):
                    mapping.default_module = val

        # Validate paths referenced in the INI
        path_issues = _validate_paths_in_ini(sys_ini, parser, category="system_settings")
        mapping.path_issues = path_issues
        issues.extend(path_issues)

        # Check module reference is valid
        if mapping.default_module and module_names:
            if mapping.default_module not in module_names:
                issue = RLIssue(
                    severity=SEVERITY_WARN,
                    category="system_mapping",
                    message=f"System '{sys_dir.name}' references module "
                            f"'{mapping.default_module}' which does not exist",
                    file=str(sys_ini),
                )
                issues.append(issue)
                mapping.path_issues.append(issue)

        mappings.append(mapping)

    return mappings, issues


def validate_global_settings(rl_root: Path) -> tuple[dict[str, Any], list[RLIssue]]:
    """Validate the global RocketLauncher.ini."""
    issues: list[RLIssue] = []
    settings: dict[str, Any] = {}

    global_ini = rl_root / "Settings" / "RocketLauncher.ini"
    if not global_ini.exists():
        # Try alternate location
        global_ini = rl_root / "RocketLauncher.ini"

    if not global_ini.exists():
        issues.append(RLIssue(
            severity=SEVERITY_WARN,
            category="global_settings",
            message="Global RocketLauncher.ini not found",
        ))
        return settings, issues

    parser = _safe_read_ini(global_ini)
    if not parser:
        issues.append(RLIssue(
            severity=SEVERITY_ERROR,
            category="global_settings",
            message="Cannot parse global RocketLauncher.ini",
            file=str(global_ini),
        ))
        return settings, issues

    # Extract key global settings
    sections = parser.sections()
    settings["sections"] = sections[:30]
    settings["ini_path"] = str(global_ini)

    # Check key paths
    path_issues = _validate_paths_in_ini(global_ini, parser, category="global_settings")
    issues.extend(path_issues)

    # Extract notable settings
    for section in sections:
        for key, val in parser.items(section):
            key_lower = key.lower()
            if key_lower in ("startdir", "rompath", "emulatorpath",
                             "emupath", "rocketlauncherpath"):
                settings[f"{section}.{key}"] = val

    return settings, issues


def validate_plugins(rl_root: Path) -> tuple[list[dict[str, Any]], list[RLIssue]]:
    """Validate RocketLauncher plugins."""
    plugins_dir = rl_root / "Plugins"
    plugins: list[dict[str, Any]] = []
    issues: list[RLIssue] = []

    if not plugins_dir.exists():
        issues.append(RLIssue(
            severity=SEVERITY_INFO,
            category="plugins",
            message="Plugins directory not found",
            file=str(plugins_dir),
        ))
        return plugins, issues

    for d in sorted(plugins_dir.iterdir()):
        if not d.is_dir():
            continue
        plugin: dict[str, Any] = {
            "name": d.name,
            "path": str(d),
            "has_ahk": bool(list(d.glob("*.ahk"))),
            "has_dll": bool(list(d.glob("*.dll"))),
            "has_ini": bool(list(d.glob("*.ini"))),
        }

        if not plugin["has_ahk"] and not plugin["has_dll"]:
            issues.append(RLIssue(
                severity=SEVERITY_INFO,
                category="plugins",
                message=f"Plugin '{d.name}' has no .ahk or .dll — may be inactive",
                file=str(d),
            ))

        # Validate paths in plugin INI if present
        for ini_file in d.glob("*.ini"):
            p = _safe_read_ini(ini_file)
            if p:
                path_issues = _validate_paths_in_ini(ini_file, p, category="plugin_config")
                issues.extend(path_issues)

        plugins.append(plugin)

    return plugins, issues


def _compute_health_score(report: RLValidationReport) -> float:
    """Compute an overall RL health score 0–100."""
    score = 0.0

    # RL exists and exe present: 40 pts
    if report.rl_exists:
        score += 20.0
    if report.exe_exists:
        score += 20.0

    # Global INI valid: 15 pts
    if report.global_ini_valid:
        score += 15.0

    # Modules present: 15 pts
    if report.module_count > 0:
        score += 10.0
        if report.module_count >= 10:
            score += 5.0

    # System settings present: 20 pts
    if report.system_count > 0:
        score += 15.0
        if report.system_count >= 10:
            score += 5.0

    # Plugins present: 10 pts
    if report.plugin_count > 0:
        score += 10.0

    # Deductions for issues
    errors = sum(1 for i in report.issues if i.severity == SEVERITY_ERROR)
    warns = sum(1 for i in report.issues if i.severity == SEVERITY_WARN)
    score -= errors * 5.0
    score -= warns * 1.0

    return round(max(0.0, min(100.0, score)), 1)


# ── Public API ──────────────────────────────────────────────────────

def validate_rl(rl_root: str | None = None) -> RLValidationReport:
    """Run a comprehensive RocketLauncher configuration validation.

    Args:
        rl_root: Path to RocketLauncher root. Falls back to config.yaml.

    Returns:
        RLValidationReport with all findings.
    """
    root_str = rl_root or cfg_get("paths.rocketlauncher_root", "")
    root = Path(root_str)
    report = RLValidationReport(rl_root=str(root))

    if not root.exists():
        report.issues.append(RLIssue(
            severity=SEVERITY_ERROR,
            category="root",
            message=f"RocketLauncher root not found: {root}",
        ))
        report.health_score = 0.0
        return report

    report.rl_exists = True

    # Check executable
    exe = root / "RocketLauncher.exe"
    report.exe_exists = exe.exists()
    report.exe_path = str(exe)
    if not exe.exists():
        report.issues.append(RLIssue(
            severity=SEVERITY_ERROR,
            category="root",
            message="RocketLauncher.exe not found",
            file=str(exe),
        ))

    # Count settings files
    settings_dir = root / "Settings"
    if settings_dir.exists():
        report.settings_file_count = len(list(settings_dir.rglob("*.ini")))

    # Validate global settings
    report.global_settings, global_issues = validate_global_settings(root)
    report.issues.extend(global_issues)
    report.global_ini_valid = not any(
        i.severity == SEVERITY_ERROR for i in global_issues
    )

    # Validate modules
    report.modules, module_issues = validate_modules(root)
    report.module_count = len(report.modules)
    report.issues.extend(module_issues)

    # Validate system settings
    module_names = {m.name for m in report.modules}
    report.system_mappings, sys_issues = validate_system_settings(root, module_names)
    report.system_count = len(report.system_mappings)
    report.issues.extend(sys_issues)

    # Validate plugins
    report.plugins, plugin_issues = validate_plugins(root)
    report.plugin_count = len(report.plugins)
    report.issues.extend(plugin_issues)

    # Compute health score
    report.health_score = _compute_health_score(report)

    log.info(
        "RL validation complete: %d modules, %d systems, %d issues, score=%.1f",
        report.module_count, report.system_count,
        len(report.issues), report.health_score,
    )
    return report


def validate_single_system(system_name: str, rl_root: str | None = None) -> dict[str, Any]:
    """Validate RocketLauncher config for a single system.

    Args:
        system_name: System name to validate.
        rl_root: Path to RocketLauncher root. Falls back to config.yaml.

    Returns:
        Dict with system mapping, module info, and issues.
    """
    root_str = rl_root or cfg_get("paths.rocketlauncher_root", "")
    root = Path(root_str)
    result: dict[str, Any] = {"system_name": system_name, "rl_root": str(root), "issues": []}

    if not root.exists():
        result["issues"].append({"severity": "error", "message": "RL root not found"})
        return result

    # Check system settings INI
    sys_dir = root / "Settings" / system_name
    sys_ini = sys_dir / f"{system_name}.ini"
    result["settings_dir_exists"] = sys_dir.exists()
    result["ini_exists"] = sys_ini.exists()

    if sys_ini.exists():
        parser = _safe_read_ini(sys_ini)
        if parser:
            result["sections"] = parser.sections()
            path_issues = _validate_paths_in_ini(sys_ini, parser, "system_settings")
            result["issues"].extend([i.to_dict() for i in path_issues])

            # Extract key settings
            settings: dict[str, str] = {}
            for section in parser.sections():
                for key, val in parser.items(section):
                    settings[f"{section}.{key}"] = val
            result["settings"] = settings
        else:
            result["issues"].append({"severity": "warn", "message": "Cannot parse INI"})

    # Check module mapping
    modules_dir = root / "Modules"
    result["module_found"] = False
    if modules_dir.exists():
        for d in modules_dir.iterdir():
            if d.is_dir() and d.name.lower() == system_name.lower():
                result["module_found"] = True
                result["module_path"] = str(d)
                break
        # Broader match
        if not result["module_found"]:
            for d in modules_dir.iterdir():
                if d.is_dir() and system_name.lower() in d.name.lower():
                    result["module_found"] = True
                    result["module_path"] = str(d)
                    break

    return result


def find_orphaned_settings(rl_root: str | None = None) -> dict[str, Any]:
    """Find system settings directories with no matching HyperSpin XML database.

    Args:
        rl_root: Path to RocketLauncher root.

    Returns:
        Dict with orphaned settings and systems without settings.
    """
    root_str = rl_root or cfg_get("paths.rocketlauncher_root", "")
    root = Path(root_str)
    hs_root = Path(cfg_get("paths.hyperspin_root", ""))
    db_root = Path(cfg_get("paths.databases_root", str(hs_root / "Databases")))

    result: dict[str, Any] = {"orphaned_settings": [], "missing_settings": []}

    if not root.exists():
        return result

    settings_dir = root / "Settings"
    if not settings_dir.exists():
        return result

    # Get system names from settings
    settings_systems = set()
    for d in settings_dir.iterdir():
        if d.is_dir() and d.name.lower() not in ("global", "rocketlauncher", "_default"):
            settings_systems.add(d.name)

    # Get system names from HyperSpin databases
    db_systems = set()
    if db_root.exists():
        for d in db_root.iterdir():
            if d.is_dir():
                db_systems.add(d.name)

    # Orphaned: in settings but not in HyperSpin
    result["orphaned_settings"] = sorted(settings_systems - db_systems)
    result["orphaned_count"] = len(result["orphaned_settings"])

    # Missing: in HyperSpin but not in settings
    result["missing_settings"] = sorted(db_systems - settings_systems)
    result["missing_count"] = len(result["missing_settings"])

    return result


def rl_summary(rl_root: str | None = None) -> dict[str, Any]:
    """Quick summary of RocketLauncher configuration status."""
    report = validate_rl(rl_root)
    return {
        "rl_root": report.rl_root,
        "exists": report.rl_exists,
        "exe_exists": report.exe_exists,
        "health_score": report.health_score,
        "module_count": report.module_count,
        "system_count": report.system_count,
        "plugin_count": report.plugin_count,
        "settings_file_count": report.settings_file_count,
        "total_issues": len(report.issues),
        "errors": sum(1 for i in report.issues if i.severity == SEVERITY_ERROR),
        "warnings": sum(1 for i in report.issues if i.severity == SEVERITY_WARN),
    }
