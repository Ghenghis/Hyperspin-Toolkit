"""M7 — Emulator Health Check.

Verifies emulator executables exist, attempts version detection, checks
RocketLauncher module wiring, and parses INI configs for broken paths.
"""
from __future__ import annotations

import configparser
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("emulator_health")

# Known emulator exe patterns — keyword in folder name → exe details
KNOWN_EMULATORS: dict[str, dict[str, Any]] = {
    "mame":           {"exe": "mame.exe",                          "version_flag": "-version",  "safe": True},
    "retroarch":      {"exe": "retroarch.exe",                     "version_flag": "--version", "safe": True},
    "dolphin":        {"exe": "Dolphin.exe",                       "version_flag": "--version", "safe": True},
    "mednafen":       {"exe": "mednafen.exe",                      "version_flag": "--version", "safe": True},
    "mupen64":        {"exe": "mupen64plus.exe",                   "version_flag": "--version", "safe": True},
    "vice":           {"exe": "x64sc.exe",                         "version_flag": "--version", "safe": True},
    "dosbox":         {"exe": "dosbox.exe",                        "version_flag": "--version", "safe": True},
    "scummvm":        {"exe": "scummvm.exe",                       "version_flag": "--version", "safe": True},
    "hatari":         {"exe": "hatari.exe",                        "version_flag": "--version", "safe": True},
    "pcsx2":          {"exe": "pcsx2.exe",                         "version_flag": "--version", "safe": False},
    "rpcs3":          {"exe": "rpcs3.exe",                         "version_flag": "--version", "safe": False},
    "ppsspp":         {"exe": "PPSSPPWindows64.exe",               "version_flag": "",          "safe": False},
    "cemu":           {"exe": "Cemu.exe",                          "version_flag": "",          "safe": False},
    "duckstation":    {"exe": "duckstation-qt-x64-ReleaseLTCG.exe","version_flag": "",          "safe": False},
    "snes9x":         {"exe": "snes9x-x64.exe",                   "version_flag": "",          "safe": False},
    "project64":      {"exe": "Project64.exe",                     "version_flag": "",          "safe": False},
    "xemu":           {"exe": "xemu.exe",                         "version_flag": "",          "safe": False},
    "demul":          {"exe": "demul.exe",                         "version_flag": "",          "safe": False},
    "model2":         {"exe": "emulator_multicpu.exe",             "version_flag": "",          "safe": False},
    "epsxe":          {"exe": "ePSXe.exe",                        "version_flag": "",          "safe": False},
    "fusion":         {"exe": "Fusion.exe",                        "version_flag": "",          "safe": False},
    "gens":           {"exe": "gens.exe",                          "version_flag": "",          "safe": False},
    "nestopia":       {"exe": "Nestopia.exe",                      "version_flag": "",          "safe": False},
    "zsnes":          {"exe": "zsnesx.exe",                        "version_flag": "",          "safe": False},
    "fbneo":          {"exe": "fbneo.exe",                         "version_flag": "",          "safe": False},
    "fba":            {"exe": "fba.exe",                           "version_flag": "",          "safe": False},
    "xenia":          {"exe": "xenia.exe",                         "version_flag": "",          "safe": False},
    "citra":          {"exe": "citra-qt.exe",                      "version_flag": "",          "safe": False},
    "lime3ds":        {"exe": "lime3ds.exe",                       "version_flag": "",          "safe": False},
    "yuzu":           {"exe": "yuzu.exe",                          "version_flag": "",          "safe": False},
    "ryujinx":        {"exe": "Ryujinx.exe",                       "version_flag": "",          "safe": False},
    "kronos":         {"exe": "kronos.exe",                        "version_flag": "",          "safe": False},
    "supermodel":     {"exe": "Supermodel.exe",                    "version_flag": "",          "safe": False},
    "applewin":       {"exe": "AppleWin.exe",                      "version_flag": "",          "safe": False},
    "winuae":         {"exe": "winuae64.exe",                      "version_flag": "",          "safe": False},
    "rocketlauncher": {"exe": "RocketLauncher.exe",                "version_flag": "",          "safe": False},
}


@dataclass
class EmulatorHealth:
    name: str
    path: str
    exe_path: str = ""
    exe_exists: bool = False
    exe_size_bytes: int = 0
    version: str = "unknown"
    is_healthy: bool = False
    health_score: float = 0.0
    config_files: list[str] = field(default_factory=list)
    config_issues: list[str] = field(default_factory=list)
    rl_module_exists: bool = False
    rl_module_path: str = ""
    issues: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "exe_path": self.exe_path,
            "exe_exists": self.exe_exists,
            "exe_size_bytes": self.exe_size_bytes,
            "version": self.version,
            "is_healthy": self.is_healthy,
            "health_score": self.health_score,
            "config_files": self.config_files,
            "config_issues": self.config_issues,
            "rl_module_exists": self.rl_module_exists,
            "rl_module_path": self.rl_module_path,
            "issues": self.issues,
        }


# ── Internal helpers ────────────────────────────────────────────────

def _find_exe(emu_dir: Path) -> tuple[str, int]:
    """Locate the primary executable for an emulator directory."""
    emu_lower = emu_dir.name.lower()

    # Try known patterns first
    for keyword, info in KNOWN_EMULATORS.items():
        if keyword in emu_lower:
            candidate = emu_dir / info["exe"]
            if candidate.exists():
                return str(candidate), candidate.stat().st_size
            # One level deeper (e.g. versioned subdirectory)
            for sub in emu_dir.iterdir():
                if sub.is_dir():
                    deep = sub / info["exe"]
                    if deep.exists():
                        return str(deep), deep.stat().st_size

    # Fallback: largest .exe in root
    exes = [f for f in emu_dir.iterdir() if f.is_file() and f.suffix.lower() == ".exe"]
    if exes:
        best = max(exes, key=lambda x: x.stat().st_size)
        return str(best), best.stat().st_size

    # Deep search
    all_exes = list(emu_dir.rglob("*.exe"))
    if all_exes:
        best = max(all_exes, key=lambda x: x.stat().st_size)
        return str(best), best.stat().st_size

    return "", 0


def _get_version(exe_path: str, version_flag: str) -> str:
    """Run exe with version flag to extract version string."""
    if not version_flag or not os.path.exists(exe_path):
        return _version_from_dirname(Path(exe_path).parent.name)
    try:
        flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        result = subprocess.run(
            [exe_path, version_flag],
            capture_output=True, text=True, timeout=6,
            creationflags=flags,
        )
        output = (result.stdout + result.stderr).strip()
        m = re.search(r"[\d]+\.[\d]+(?:\.[\d]+)?(?:\.[\d]+)?", output)
        if m:
            return m.group(0)
        return output[:40] if output else "unknown"
    except Exception:
        return _version_from_dirname(Path(exe_path).parent.name)


def _version_from_dirname(name: str) -> str:
    """Extract version number from a folder name like 'mame0268' or 'MAME 0.268'."""
    m = re.search(r"[\d]+\.[\d]+(?:\.[\d]+)?", name)
    if m:
        return m.group(0)
    m = re.search(r"0[\d]{2,}", name)
    if m:
        return m.group(0)
    m = re.search(r"[\d]{3,}", name)
    if m:
        return m.group(0)
    return "unknown"


def _check_configs(emu_dir: Path) -> tuple[list[str], list[str]]:
    """Find config files and flag broken absolute paths inside INIs."""
    cfg_exts = {".ini", ".cfg", ".conf", ".json", ".xml", ".toml"}
    configs = [
        str(f) for f in emu_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in cfg_exts
    ][:20]
    issues: list[str] = []

    for cfg_path in configs[:6]:
        p = Path(cfg_path)
        if p.suffix.lower() != ".ini":
            continue
        try:
            parser = configparser.ConfigParser(strict=False)
            parser.read(str(p), encoding="utf-8-sig")
            for section in parser.sections():
                for key, val in parser.items(section):
                    # Detect Windows absolute paths that no longer exist
                    m = re.match(r"^([A-Za-z]):\\", val)
                    if m:
                        clean = val.split(";")[0].strip()
                        if not os.path.exists(clean):
                            issues.append(
                                f"{p.name}: [{section}]{key} = {val[:70]} — path missing"
                            )
        except Exception:
            pass

    return configs, issues


def _check_rl_module(emu_name: str, rl_root: str) -> tuple[bool, str]:
    """Check if a RocketLauncher module exists for this emulator."""
    if not rl_root or not os.path.exists(rl_root):
        return False, ""
    modules_dir = Path(rl_root) / "Modules"
    if not modules_dir.exists():
        return False, ""

    emu_lower = emu_name.lower()

    # Exact match
    exact = modules_dir / emu_name
    if exact.exists():
        return True, str(exact)

    # Case-insensitive fuzzy match
    for d in modules_dir.iterdir():
        if d.is_dir() and emu_lower in d.name.lower():
            return True, str(d)

    return False, ""


def _score_health(h: EmulatorHealth) -> float:
    """Compute a 0-100 health score for one emulator."""
    score = 0.0
    if h.exe_exists:
        score += 50.0
    if h.exe_size_bytes > 100 * 1024:  # > 100 KB
        score += 10.0
    if h.version != "unknown":
        score += 10.0
    if h.config_files:
        score += 10.0
    if not h.config_issues:
        score += 10.0
    if h.rl_module_exists:
        score += 10.0
    return round(score, 1)


# ── Public API ──────────────────────────────────────────────────────

def check_emulator(emu_dir: Path, rl_root: str = "") -> EmulatorHealth:
    """Run a full health check on a single emulator directory."""
    h = EmulatorHealth(name=emu_dir.name, path=str(emu_dir))

    if not emu_dir.exists():
        h.issues.append({"severity": "error", "msg": f"Directory not found: {emu_dir}"})
        return h

    # --- executable ---
    h.exe_path, h.exe_size_bytes = _find_exe(emu_dir)
    h.exe_exists = bool(h.exe_path) and os.path.exists(h.exe_path)

    if not h.exe_exists:
        h.issues.append({"severity": "warn", "msg": "No .exe found in emulator directory"})
    else:
        emu_lower = emu_dir.name.lower()
        version_flag = ""
        safe_launch = False
        for keyword, info in KNOWN_EMULATORS.items():
            if keyword in emu_lower:
                version_flag = info.get("version_flag", "")
                safe_launch = info.get("safe", False)
                break
        if safe_launch and version_flag:
            h.version = _get_version(h.exe_path, version_flag)
        else:
            h.version = _version_from_dirname(emu_dir.name)

    # --- configs ---
    h.config_files, h.config_issues = _check_configs(emu_dir)
    for issue in h.config_issues:
        h.issues.append({"severity": "warn", "msg": issue})

    # --- RocketLauncher module ---
    h.rl_module_exists, h.rl_module_path = _check_rl_module(emu_dir.name, rl_root)
    if not h.rl_module_exists and rl_root and os.path.exists(rl_root):
        h.issues.append({"severity": "info", "msg": f"No RocketLauncher module found for {emu_dir.name}"})

    h.health_score = _score_health(h)
    h.is_healthy = h.exe_exists and h.health_score >= 60.0

    return h


def check_all_emulators(
    emu_root: str | None = None,
    rl_root: str | None = None,
) -> list[dict[str, Any]]:
    """Check health of all emulator directories under *emu_root*."""
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", ""))
    rl_path  = str(rl_root or cfg_get("paths.rocketlauncher_root", ""))

    if not emu_path.exists():
        log.warning("Emulators root not found: %s", emu_path)
        return []

    results: list[dict[str, Any]] = []
    for entry in sorted(emu_path.iterdir()):
        if not entry.is_dir():
            continue
        h = check_emulator(entry, rl_root=rl_path)
        results.append(h.to_dict())
        log.debug("Emulator %s: healthy=%s score=%.0f", entry.name, h.is_healthy, h.health_score)

    log.info(
        "Checked %d emulators: %d healthy",
        len(results), sum(1 for r in results if r["is_healthy"]),
    )
    return results


def check_single_emulator(name_or_path: str) -> dict[str, Any]:
    """Check one emulator by name (relative to emulators_root) or full path."""
    p = Path(name_or_path)
    if not p.is_absolute():
        emu_root = Path(cfg_get("paths.emulators_root", ""))
        p = emu_root / name_or_path
    if not p.exists():
        return {"error": f"Emulator not found: {name_or_path}"}
    rl_root = cfg_get("paths.rocketlauncher_root", "")
    return check_emulator(p, rl_root=str(rl_root)).to_dict()


def health_summary(
    emu_root: str | None = None,
    rl_root: str | None = None,
) -> dict[str, Any]:
    """Return aggregated emulator ecosystem health."""
    results = check_all_emulators(emu_root=emu_root, rl_root=rl_root)
    healthy   = [r for r in results if r["is_healthy"]]
    unhealthy = [r for r in results if not r["is_healthy"]]
    scores    = [r["health_score"] for r in results if r["health_score"] > 0]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    return {
        "total":           len(results),
        "healthy":         len(healthy),
        "unhealthy":       len(unhealthy),
        "avg_health_score": avg_score,
        "emulators":       results,
        "critical_issues": [
            {"emulator": r["name"], "issues": r["issues"]}
            for r in unhealthy
            if r["issues"]
        ][:20],
    }
