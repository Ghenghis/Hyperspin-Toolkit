"""M13 — Dependency Conflict Detector.

Maps DLL, runtime, and shared library dependencies for emulators/tools.
Detects version conflicts, warns before updates that would break deps,
and suggests resolution strategies.
"""
from __future__ import annotations

import os
import re
import struct
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger, audit

log = get_logger("dependency_detector")

# ---------------------------------------------------------------------------
# Known shared runtimes that commonly cause conflicts
# ---------------------------------------------------------------------------
KNOWN_RUNTIMES = {
    "vcruntime140.dll":     "Visual C++ 2015-2022 Redistributable",
    "vcruntime140_1.dll":   "Visual C++ 2015-2022 Redistributable (x64)",
    "msvcp140.dll":         "Visual C++ 2015-2022 Redistributable",
    "msvcp140_1.dll":       "Visual C++ 2015-2022 Redistributable",
    "ucrtbase.dll":         "Universal C Runtime",
    "api-ms-win-crt-runtime-l1-1-0.dll": "Universal CRT",
    "d3d9.dll":             "DirectX 9 Runtime",
    "d3d11.dll":            "DirectX 11 Runtime",
    "d3d12.dll":            "DirectX 12 Runtime",
    "d3dcompiler_47.dll":   "DirectX Shader Compiler",
    "xinput1_3.dll":        "XInput (DirectX Input)",
    "xinput1_4.dll":        "XInput 1.4 (Windows 8+)",
    "sdl2.dll":             "SDL2 Library",
    "sdl.dll":              "SDL1 Library",
    "opengl32.dll":         "OpenGL",
    "vulkan-1.dll":         "Vulkan Runtime",
    "libretro.dll":         "libretro Core",
    "zlib1.dll":            "zlib Compression",
    "libpng16.dll":         "libpng",
    "qt5core.dll":          "Qt 5 Framework",
    "qt6core.dll":          "Qt 6 Framework",
    "qt5widgets.dll":       "Qt 5 Widgets",
    "qt6widgets.dll":       "Qt 6 Widgets",
}

# Common DLL patterns to detect (case-insensitive)
DLL_PATTERNS = [
    r"vcruntime\d+.*\.dll",
    r"msvcp\d+.*\.dll",
    r"msvcr\d+.*\.dll",
    r"d3d\d+\.dll",
    r"d3dcompiler.*\.dll",
    r"xinput.*\.dll",
    r"sdl2?\.dll",
    r"qt[56].*\.dll",
    r"libretro.*\.dll",
    r"vulkan.*\.dll",
    r"openal.*\.dll",
]


@dataclass
class DllInfo:
    """Information about a DLL file."""
    name: str
    path: str
    size_bytes: int = 0
    version: str = ""
    runtime_name: str = ""
    is_system: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "size_bytes": self.size_bytes,
            "version": self.version,
            "runtime_name": self.runtime_name,
            "is_system": self.is_system,
        }


@dataclass
class Conflict:
    """A detected dependency conflict."""
    dll_name: str
    severity: str  # critical, warning, info
    message: str
    emulators: list[str] = field(default_factory=list)
    versions: list[str] = field(default_factory=list)
    resolution: str = ""

    def to_dict(self) -> dict:
        return {
            "dll_name": self.dll_name,
            "severity": self.severity,
            "message": self.message,
            "emulators": self.emulators,
            "versions": self.versions,
            "resolution": self.resolution,
        }


# ---------------------------------------------------------------------------
# DLL scanning
# ---------------------------------------------------------------------------

def _get_dll_version(dll_path: Path) -> str:
    """Try to extract the file version from a DLL using Windows API or file size heuristic."""
    if sys.platform == "win32":
        try:
            import ctypes
            size = ctypes.windll.version.GetFileVersionInfoSizeW(str(dll_path), None)
            if size:
                data = ctypes.create_string_buffer(size)
                ctypes.windll.version.GetFileVersionInfoW(str(dll_path), 0, size, data)
                buf = ctypes.c_void_p()
                buf_len = ctypes.c_uint()
                if ctypes.windll.version.VerQueryValueW(
                    data, r"\VarFileInfo\Translation", ctypes.byref(buf), ctypes.byref(buf_len)
                ):
                    pass
                if ctypes.windll.version.VerQueryValueW(
                    data, "\\", ctypes.byref(buf), ctypes.byref(buf_len)
                ):
                    vs = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
                    ms = vs[2]
                    ls = vs[3]
                    return f"{(ms >> 16) & 0xFFFF}.{ms & 0xFFFF}.{(ls >> 16) & 0xFFFF}.{ls & 0xFFFF}"
        except Exception:
            pass

    # Fallback: use file modification date
    try:
        from datetime import datetime
        mtime = datetime.fromtimestamp(dll_path.stat().st_mtime)
        return f"unknown ({mtime.strftime('%Y-%m-%d')})"
    except Exception:
        return "unknown"


def scan_emulator_dlls(emu_dir: Path, max_depth: int = 2) -> list[DllInfo]:
    """Scan an emulator directory for DLL files."""
    dlls = []
    try:
        for f in emu_dir.rglob("*.dll"):
            # Respect max depth
            rel = f.relative_to(emu_dir)
            if len(rel.parts) > max_depth + 1:
                continue

            name_lower = f.name.lower()
            is_known = name_lower in KNOWN_RUNTIMES
            is_pattern = any(re.match(p, name_lower) for p in DLL_PATTERNS)

            if is_known or is_pattern:
                info = DllInfo(
                    name=f.name.lower(),
                    path=str(f),
                    size_bytes=f.stat().st_size,
                    version=_get_dll_version(f),
                    runtime_name=KNOWN_RUNTIMES.get(name_lower, ""),
                    is_system=False,
                )
                dlls.append(info)
    except Exception as exc:
        log.warning("Error scanning %s: %s", emu_dir, exc)

    return dlls


def scan_all_dependencies(emu_root: str | None = None) -> dict[str, list[DllInfo]]:
    """Scan all emulator directories for shared library dependencies.

    Returns: {emulator_name: [DllInfo, ...]}
    """
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", ""))
    if not emu_path.exists():
        log.warning("Emulators root not found: %s", emu_path)
        return {}

    result: dict[str, list[DllInfo]] = {}
    for entry in sorted(emu_path.iterdir()):
        if not entry.is_dir():
            continue
        dlls = scan_emulator_dlls(entry)
        if dlls:
            result[entry.name] = dlls
            log.debug("%s: %d shared DLLs found", entry.name, len(dlls))

    log.info("Scanned %d emulators for dependencies", len(result))
    return result


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def detect_conflicts(dep_map: dict[str, list[DllInfo]] | None = None,
                     emu_root: str | None = None) -> list[Conflict]:
    """Detect version conflicts in shared libraries across emulators.

    Checks for:
    1. Same DLL with different file sizes (likely different versions)
    2. Conflicting runtime versions (e.g., VC++ 2013 vs 2022)
    3. Qt version mixing (Qt5 vs Qt6)
    """
    if dep_map is None:
        dep_map = scan_all_dependencies(emu_root)

    # Build reverse index: dll_name -> [(emulator, DllInfo), ...]
    dll_index: dict[str, list[tuple[str, DllInfo]]] = defaultdict(list)
    for emu_name, dlls in dep_map.items():
        for dll in dlls:
            dll_index[dll.name].append((emu_name, dll))

    conflicts: list[Conflict] = []

    for dll_name, entries in dll_index.items():
        if len(entries) < 2:
            continue

        # Check for size differences (indicates different versions)
        sizes = set(info.size_bytes for _, info in entries)
        if len(sizes) > 1:
            emus = [emu for emu, _ in entries]
            versions = [f"{info.size_bytes:,}B" for _, info in entries]

            severity = "warning"
            runtime = KNOWN_RUNTIMES.get(dll_name, "")
            if "visual c++" in runtime.lower() or "crt" in runtime.lower():
                severity = "critical"

            conflicts.append(Conflict(
                dll_name=dll_name,
                severity=severity,
                message=f"Different versions of {dll_name} found across {len(emus)} emulators ({runtime or 'shared library'})",
                emulators=emus,
                versions=versions,
                resolution=_suggest_resolution(dll_name, entries),
            ))

    # Check for Qt version mixing
    qt5_emus = set()
    qt6_emus = set()
    for emu_name, dlls in dep_map.items():
        for dll in dlls:
            if dll.name.startswith("qt5"):
                qt5_emus.add(emu_name)
            elif dll.name.startswith("qt6"):
                qt6_emus.add(emu_name)
    mixed = qt5_emus & qt6_emus
    if mixed:
        conflicts.append(Conflict(
            dll_name="Qt5/Qt6",
            severity="info",
            message=f"{len(mixed)} emulator(s) bundle both Qt5 and Qt6 libraries",
            emulators=list(mixed),
            resolution="Usually safe — each emulator uses its own bundled Qt. Only a concern if they share a common plugin directory.",
        ))

    return conflicts


def _suggest_resolution(dll_name: str, entries: list[tuple[str, DllInfo]]) -> str:
    """Suggest a resolution strategy for a DLL conflict."""
    runtime = KNOWN_RUNTIMES.get(dll_name, "")
    if "visual c++" in runtime.lower():
        return (
            "Install the latest Visual C++ Redistributable from Microsoft. "
            "Each emulator should use its own bundled copy — conflicts usually "
            "only matter if they share a PATH directory."
        )
    if "directx" in runtime.lower():
        return "Run the DirectX End-User Runtime installer to ensure all versions are available."
    if "sdl" in dll_name.lower():
        return "Each emulator typically bundles its own SDL. Ensure each emulator folder has its own copy."
    if "qt" in dll_name.lower():
        return "Qt libraries are usually self-contained per emulator. No action needed unless emulators share a folder."
    return "Ensure each emulator has its own copy of this DLL in its directory. Avoid sharing DLLs via system PATH."


# ---------------------------------------------------------------------------
# Pre-update conflict check
# ---------------------------------------------------------------------------

def check_update_conflicts(emulator_name: str, update_dir: str | None = None,
                           emu_root: str | None = None) -> dict:
    """Check if updating an emulator would introduce dependency conflicts.

    Scans the update package for DLLs and compares against existing emulator DLLs.
    """
    emu_path = Path(emu_root or cfg_get("paths.emulators_root", ""))
    emu_dir = emu_path / emulator_name

    if not emu_dir.exists():
        return {"error": f"Emulator directory not found: {emu_dir}"}

    current_dlls = {d.name: d for d in scan_emulator_dlls(emu_dir)}

    # If update_dir provided, scan it for new DLLs
    new_dlls: dict[str, DllInfo] = {}
    if update_dir and Path(update_dir).exists():
        for dll in scan_emulator_dlls(Path(update_dir)):
            new_dlls[dll.name] = dll

    changes = {
        "added": [],
        "removed": [],
        "changed": [],
        "unchanged": [],
    }

    all_names = set(current_dlls.keys()) | set(new_dlls.keys())
    for name in sorted(all_names):
        old = current_dlls.get(name)
        new = new_dlls.get(name)
        if old and not new:
            changes["removed"].append(old.to_dict())
        elif new and not old:
            changes["added"].append(new.to_dict())
        elif old and new and old.size_bytes != new.size_bytes:
            changes["changed"].append({
                "dll": name,
                "old_size": old.size_bytes,
                "new_size": new.size_bytes,
                "runtime": old.runtime_name or new.runtime_name,
            })
        elif old and new:
            changes["unchanged"].append(name)

    # Check for potential cross-emulator conflicts
    all_deps = scan_all_dependencies(emu_root)
    potential_issues = []
    for name, new_dll in new_dlls.items():
        for other_emu, other_dlls in all_deps.items():
            if other_emu == emulator_name:
                continue
            for odll in other_dlls:
                if odll.name == name and odll.size_bytes != new_dll.size_bytes:
                    potential_issues.append({
                        "dll": name,
                        "other_emulator": other_emu,
                        "other_size": odll.size_bytes,
                        "new_size": new_dll.size_bytes,
                        "risk": "low" if name not in KNOWN_RUNTIMES else "medium",
                    })

    return {
        "emulator": emulator_name,
        "current_dll_count": len(current_dlls),
        "update_dll_count": len(new_dlls),
        "changes": changes,
        "potential_cross_conflicts": potential_issues,
        "safe_to_update": len(potential_issues) == 0,
    }


# ---------------------------------------------------------------------------
# Summary / public API
# ---------------------------------------------------------------------------

def dependency_report(emu_root: str | None = None) -> dict:
    """Generate a full dependency analysis report."""
    dep_map = scan_all_dependencies(emu_root)
    conflicts = detect_conflicts(dep_map)

    # Aggregate stats
    total_dlls = sum(len(v) for v in dep_map.values())
    unique_dlls = len(set(d.name for dlls in dep_map.values() for d in dlls))
    runtime_usage: dict[str, int] = defaultdict(int)
    for dlls in dep_map.values():
        for d in dlls:
            if d.runtime_name:
                runtime_usage[d.runtime_name] += 1

    critical = [c for c in conflicts if c.severity == "critical"]
    warnings = [c for c in conflicts if c.severity == "warning"]
    infos = [c for c in conflicts if c.severity == "info"]

    audit("dependency_scan", f"Scanned {len(dep_map)} emulators, {len(conflicts)} conflicts")

    return {
        "emulators_scanned": len(dep_map),
        "total_shared_dlls": total_dlls,
        "unique_dlls": unique_dlls,
        "conflicts": {
            "critical": len(critical),
            "warning": len(warnings),
            "info": len(infos),
            "total": len(conflicts),
            "details": [c.to_dict() for c in conflicts],
        },
        "runtime_usage": dict(sorted(runtime_usage.items(), key=lambda x: -x[1])),
        "per_emulator": {
            name: {
                "dll_count": len(dlls),
                "dlls": [d.to_dict() for d in dlls],
            }
            for name, dlls in dep_map.items()
        },
    }


def dependency_summary(emu_root: str | None = None) -> dict:
    """Quick summary without full per-emulator details."""
    dep_map = scan_all_dependencies(emu_root)
    conflicts = detect_conflicts(dep_map)

    return {
        "emulators_scanned": len(dep_map),
        "total_shared_dlls": sum(len(v) for v in dep_map.values()),
        "unique_dlls": len(set(d.name for dlls in dep_map.values() for d in dlls)),
        "conflicts_critical": sum(1 for c in conflicts if c.severity == "critical"),
        "conflicts_warning": sum(1 for c in conflicts if c.severity == "warning"),
        "conflicts_info": sum(1 for c in conflicts if c.severity == "info"),
        "conflicts_total": len(conflicts),
        "conflict_details": [c.to_dict() for c in conflicts],
    }
