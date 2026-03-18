"""M59 — RocketLauncher Fade, Bezel & Pause Media Manager.

Scans and validates RocketLauncher media directories for fade images,
bezel overlays, and pause screen assets.  Produces per-system coverage
reports with severity-tagged issues and supports global/per-system/per-ROM
configuration awareness.

Directory layout expected:
    RocketLauncher/
      Media/
        Fade/{System}/          ← Multi-layer fade PNGs (Layer 1-4)
        Bezels/{System}/        ← Bezel overlays + backgrounds
        Pause/{System}/         ← Game guides, controller images
      Settings/{System}/        ← Per-system INI with [Fade], [Bezel], [Pause] sections
"""
from __future__ import annotations

import configparser
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("rl_media_manager")

# ── Constants ────────────────────────────────────────────────────────
SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"

VALID_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif"}
FADE_LAYER_NAMES = ["Layer 1", "Layer 2", "Layer 3", "Layer 4"]
MAX_BEZEL_WIDTH = 3840
MAX_BEZEL_HEIGHT = 2160

# Standard RocketLauncher media sub-directories
MEDIA_TYPES = {
    "fade": "Fade",
    "bezels": "Bezels",
    "pause": "Pause",
}

# Pause asset sub-categories
PAUSE_CATEGORIES = {
    "Guides":     [".pdf", ".txt", ".png", ".jpg", ".zip", ".7z", ".rar"],
    "Controls":   [".png", ".jpg", ".jpeg", ".bmp"],
    "Extra":      [".png", ".jpg", ".jpeg", ".mp4", ".avi"],
}


# ── Data Classes ─────────────────────────────────────────────────────

@dataclass
class MediaIssue:
    """A single media validation issue."""
    severity: str
    category: str  # fade / bezel / pause
    system: str
    message: str
    file: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, str]:
        d = {
            "severity": self.severity,
            "category": self.category,
            "system": self.system,
            "message": self.message,
        }
        if self.file:
            d["file"] = self.file
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class FadeAsset:
    """A single fade image asset."""
    system: str
    game: str = ""          # Empty = global/system-level
    layer: int = 1          # 1-4
    path: str = ""
    width: int = 0
    height: int = 0
    is_png: bool = False
    file_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "game": self.game,
            "layer": self.layer,
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "is_png": self.is_png,
            "file_size": self.file_size,
        }


@dataclass
class BezelAsset:
    """A single bezel overlay asset."""
    system: str
    game: str = ""
    path: str = ""
    width: int = 0
    height: int = 0
    has_background: bool = False
    background_path: str = ""
    orientation: str = "horizontal"  # horizontal / vertical
    file_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "game": self.game,
            "path": self.path,
            "width": self.width,
            "height": self.height,
            "has_background": self.has_background,
            "background_path": self.background_path,
            "orientation": self.orientation,
            "file_size": self.file_size,
        }


@dataclass
class PauseAsset:
    """A pause screen asset (guide, controller map, etc.)."""
    system: str
    game: str = ""
    category: str = ""       # Guides / Controls / Extra
    path: str = ""
    file_ext: str = ""
    file_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "game": self.game,
            "category": self.category,
            "path": self.path,
            "file_ext": self.file_ext,
            "file_size": self.file_size,
        }


@dataclass
class SystemCoverage:
    """Coverage report for a single system."""
    system: str
    fade_count: int = 0
    fade_layers: dict[int, int] = field(default_factory=dict)
    bezel_count: int = 0
    bezel_per_game: int = 0
    pause_count: int = 0
    pause_guides: int = 0
    pause_controls: int = 0
    game_count: int = 0         # From RL Settings ROM list if available
    fade_coverage_pct: float = 0.0
    bezel_coverage_pct: float = 0.0
    pause_coverage_pct: float = 0.0
    total_size_bytes: int = 0
    issues: list[MediaIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "fade_count": self.fade_count,
            "fade_layers": self.fade_layers,
            "bezel_count": self.bezel_count,
            "bezel_per_game": self.bezel_per_game,
            "pause_count": self.pause_count,
            "pause_guides": self.pause_guides,
            "pause_controls": self.pause_controls,
            "game_count": self.game_count,
            "fade_coverage_pct": round(self.fade_coverage_pct, 1),
            "bezel_coverage_pct": round(self.bezel_coverage_pct, 1),
            "pause_coverage_pct": round(self.pause_coverage_pct, 1),
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 1),
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class RLMediaReport:
    """Full RocketLauncher media scan report."""
    rl_root: str
    systems_scanned: int = 0
    total_fade: int = 0
    total_bezels: int = 0
    total_pause: int = 0
    total_size_bytes: int = 0
    total_issues: int = 0
    systems: list[SystemCoverage] = field(default_factory=list)
    issues: list[MediaIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rl_root": self.rl_root,
            "systems_scanned": self.systems_scanned,
            "total_fade": self.total_fade,
            "total_bezels": self.total_bezels,
            "total_pause": self.total_pause,
            "total_size_mb": round(self.total_size_bytes / (1024 * 1024), 1),
            "total_issues": self.total_issues,
            "summary": {
                "errors": sum(1 for i in self.issues if i.severity == SEVERITY_ERROR),
                "warnings": sum(1 for i in self.issues if i.severity == SEVERITY_WARN),
                "info": sum(1 for i in self.issues if i.severity == SEVERITY_INFO),
            },
            "systems": [s.to_dict() for s in self.systems],
        }


# ── Image Dimension Helpers ──────────────────────────────────────────

def _get_png_dimensions(filepath: Path) -> tuple[int, int]:
    """Read PNG width/height from IHDR chunk without PIL."""
    try:
        with open(filepath, "rb") as f:
            sig = f.read(8)
            if sig[:4] != b"\x89PNG":
                return 0, 0
            f.read(4)  # chunk length
            chunk_type = f.read(4)
            if chunk_type != b"IHDR":
                return 0, 0
            w = struct.unpack(">I", f.read(4))[0]
            h = struct.unpack(">I", f.read(4))[0]
            return w, h
    except Exception:
        return 0, 0


def _get_image_dimensions(filepath: Path) -> tuple[int, int]:
    """Get image dimensions for PNG files (primary format for RL media)."""
    ext = filepath.suffix.lower()
    if ext == ".png":
        return _get_png_dimensions(filepath)
    # For non-PNG, return 0,0 — validation will flag non-PNG fades/bezels
    return 0, 0


def _detect_orientation(width: int, height: int) -> str:
    """Detect if an image is horizontal or vertical layout."""
    if width == 0 or height == 0:
        return "unknown"
    return "vertical" if height > width else "horizontal"


# ── INI Helpers ──────────────────────────────────────────────────────

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


def _get_rom_list(rl_root: Path, system: str) -> list[str]:
    """Get list of known ROM names for a system from RL Settings INI."""
    sys_ini = rl_root / "Settings" / system / f"{system}.ini"
    if not sys_ini.exists():
        return []
    parser = _safe_read_ini(sys_ini)
    if not parser:
        return []
    # RL stores ROM paths in various sections — try to extract game names
    rom_path = ""
    for section in parser.sections():
        for key in ("rompath", "rom_path", "roms_path"):
            if parser.has_option(section, key):
                rom_path = parser.get(section, key).strip().strip('"')
                break
    if rom_path and os.path.isdir(rom_path):
        return [f.stem for f in Path(rom_path).iterdir()
                if f.is_file() and not f.name.startswith(".")]
    return []


# ── Fade Scanner ─────────────────────────────────────────────────────

def scan_fade(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Scan fade images for a single system.

    Fade directories: RocketLauncher/Media/Fade/{System}/
    Layers 1-4 are stored as separate PNG files.

    Returns dict with assets, coverage, and issues.
    """
    root = _get_rl_root(rl_root)
    fade_dir = root / "Media" / "Fade" / system
    issues: list[MediaIssue] = []
    assets: list[FadeAsset] = []

    if not fade_dir.exists():
        issues.append(MediaIssue(
            severity=SEVERITY_INFO,
            category="fade",
            system=system,
            message=f"No fade directory found for {system}",
            suggestion=f"Create {fade_dir}",
        ))
        return {
            "system": system,
            "fade_dir": str(fade_dir),
            "exists": False,
            "assets": [],
            "issues": [i.to_dict() for i in issues],
        }

    total_size = 0
    layer_counts: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}

    # Scan for fade images — both system-level and per-game subdirs
    for item in sorted(fade_dir.rglob("*")):
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext not in VALID_IMAGE_EXTS:
            continue

        size = item.stat().st_size
        total_size += size
        w, h = _get_image_dimensions(item)
        is_png = ext == ".png"

        # Determine layer from filename or parent directory
        layer = _detect_layer(item)

        # Determine if per-game or system-level
        rel = item.relative_to(fade_dir)
        game = rel.parts[0] if len(rel.parts) > 1 else ""

        asset = FadeAsset(
            system=system,
            game=game,
            layer=layer,
            path=str(item),
            width=w,
            height=h,
            is_png=is_png,
            file_size=size,
        )
        assets.append(asset)

        if layer in layer_counts:
            layer_counts[layer] += 1

        # Validate format
        if not is_png:
            issues.append(MediaIssue(
                severity=SEVERITY_WARN,
                category="fade",
                system=system,
                message=f"Fade image is not PNG: {item.name}",
                file=str(item),
                suggestion="Convert to PNG for RocketLauncher compatibility",
            ))

        # Validate dimensions (if readable)
        if is_png and (w == 0 or h == 0):
            issues.append(MediaIssue(
                severity=SEVERITY_WARN,
                category="fade",
                system=system,
                message=f"Cannot read dimensions: {item.name}",
                file=str(item),
            ))

    return {
        "system": system,
        "fade_dir": str(fade_dir),
        "exists": True,
        "asset_count": len(assets),
        "layer_counts": layer_counts,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "assets": [a.to_dict() for a in assets[:200]],
        "issues": [i.to_dict() for i in issues],
    }


def _detect_layer(filepath: Path) -> int:
    """Detect fade layer number from filename or parent dir."""
    name = filepath.stem.lower()
    parent = filepath.parent.name.lower()

    for layer_num in range(1, 5):
        markers = [f"layer {layer_num}", f"layer{layer_num}", f"_l{layer_num}",
                    f"-l{layer_num}", f"fade{layer_num}"]
        for marker in markers:
            if marker in name or marker in parent:
                return layer_num
    # Default to layer 1
    return 1


# ── Bezel Scanner ────────────────────────────────────────────────────

def scan_bezels(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Scan bezel overlays for a single system.

    Bezel directories: RocketLauncher/Media/Bezels/{System}/
    Per-game bezels: {System}/{GameName}.png
    Backgrounds: {System}/{GameName}_Background.png or Backgrounds/{GameName}.png

    Returns dict with assets, coverage, orientation detection, and issues.
    """
    root = _get_rl_root(rl_root)
    bezel_dir = root / "Media" / "Bezels" / system
    issues: list[MediaIssue] = []
    assets: list[BezelAsset] = []

    if not bezel_dir.exists():
        issues.append(MediaIssue(
            severity=SEVERITY_INFO,
            category="bezels",
            system=system,
            message=f"No bezel directory found for {system}",
            suggestion=f"Create {bezel_dir}",
        ))
        return {
            "system": system,
            "bezel_dir": str(bezel_dir),
            "exists": False,
            "assets": [],
            "issues": [i.to_dict() for i in issues],
        }

    total_size = 0
    orientations = {"horizontal": 0, "vertical": 0, "unknown": 0}
    background_map: dict[str, str] = {}

    # First pass: collect background images
    bg_dir = bezel_dir / "Backgrounds"
    if bg_dir.exists():
        for bg_file in bg_dir.iterdir():
            if bg_file.is_file() and bg_file.suffix.lower() in VALID_IMAGE_EXTS:
                background_map[bg_file.stem.lower()] = str(bg_file)

    # Second pass: scan all bezel images
    for item in sorted(bezel_dir.iterdir()):
        if not item.is_file():
            continue
        ext = item.suffix.lower()
        if ext not in VALID_IMAGE_EXTS:
            continue

        # Skip background files at root
        if "_background" in item.stem.lower():
            continue

        size = item.stat().st_size
        total_size += size
        w, h = _get_image_dimensions(item)
        orientation = _detect_orientation(w, h)
        orientations[orientation] = orientations.get(orientation, 0) + 1

        game = item.stem
        has_bg = (game.lower() in background_map or
                  (bezel_dir / f"{game}_Background.png").exists())
        bg_path = background_map.get(game.lower(), "")
        if not bg_path:
            bg_check = bezel_dir / f"{game}_Background.png"
            if bg_check.exists():
                bg_path = str(bg_check)

        asset = BezelAsset(
            system=system,
            game=game,
            path=str(item),
            width=w,
            height=h,
            has_background=has_bg,
            background_path=bg_path,
            orientation=orientation,
            file_size=size,
        )
        assets.append(asset)

        # Validate dimensions for bezels
        if w > 0 and h > 0:
            if w > MAX_BEZEL_WIDTH or h > MAX_BEZEL_HEIGHT:
                issues.append(MediaIssue(
                    severity=SEVERITY_WARN,
                    category="bezels",
                    system=system,
                    message=f"Bezel exceeds 4K resolution: {w}x{h}",
                    file=str(item),
                    suggestion=f"Resize to {MAX_BEZEL_WIDTH}x{MAX_BEZEL_HEIGHT} or lower",
                ))

    # Also scan per-game subdirectories
    for subdir in sorted(bezel_dir.iterdir()):
        if not subdir.is_dir() or subdir.name.lower() == "backgrounds":
            continue
        for item in subdir.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lower()
            if ext not in VALID_IMAGE_EXTS:
                continue
            if "_background" in item.stem.lower():
                continue

            size = item.stat().st_size
            total_size += size
            w, h = _get_image_dimensions(item)
            orientation = _detect_orientation(w, h)

            asset = BezelAsset(
                system=system,
                game=subdir.name,
                path=str(item),
                width=w,
                height=h,
                orientation=orientation,
                file_size=size,
            )
            assets.append(asset)

    return {
        "system": system,
        "bezel_dir": str(bezel_dir),
        "exists": True,
        "asset_count": len(assets),
        "orientations": orientations,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "assets": [a.to_dict() for a in assets[:200]],
        "issues": [i.to_dict() for i in issues],
    }


# ── Pause Scanner ────────────────────────────────────────────────────

def scan_pause(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Scan pause screen assets for a single system.

    Pause directories: RocketLauncher/Media/Pause/{System}/
    Sub-categories: Guides/, Controls/, Extra/ or flat per-game assets.

    Returns dict with categorized assets and issues.
    """
    root = _get_rl_root(rl_root)
    pause_dir = root / "Media" / "Pause" / system
    issues: list[MediaIssue] = []
    assets: list[PauseAsset] = []

    if not pause_dir.exists():
        issues.append(MediaIssue(
            severity=SEVERITY_INFO,
            category="pause",
            system=system,
            message=f"No pause directory found for {system}",
            suggestion=f"Create {pause_dir}",
        ))
        return {
            "system": system,
            "pause_dir": str(pause_dir),
            "exists": False,
            "assets": [],
            "issues": [i.to_dict() for i in issues],
        }

    total_size = 0
    category_counts: dict[str, int] = {"Guides": 0, "Controls": 0, "Extra": 0, "Other": 0}

    for item in sorted(pause_dir.rglob("*")):
        if not item.is_file():
            continue

        size = item.stat().st_size
        total_size += size
        ext = item.suffix.lower()

        # Determine category from parent directory or extension
        category = _classify_pause_asset(item, pause_dir)
        category_counts[category] = category_counts.get(category, 0) + 1

        # Determine game name
        rel = item.relative_to(pause_dir)
        game = ""
        if len(rel.parts) > 1:
            # Could be {Category}/{Game}.ext or {Game}/{file}.ext
            if rel.parts[0] in PAUSE_CATEGORIES:
                game = item.stem
            else:
                game = rel.parts[0]
        else:
            game = item.stem

        asset = PauseAsset(
            system=system,
            game=game,
            category=category,
            path=str(item),
            file_ext=ext,
            file_size=size,
        )
        assets.append(asset)

    return {
        "system": system,
        "pause_dir": str(pause_dir),
        "exists": True,
        "asset_count": len(assets),
        "category_counts": category_counts,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "assets": [a.to_dict() for a in assets[:200]],
        "issues": [i.to_dict() for i in issues],
    }


def _classify_pause_asset(filepath: Path, pause_root: Path) -> str:
    """Classify a pause asset into Guides/Controls/Extra/Other."""
    rel = filepath.relative_to(pause_root)
    ext = filepath.suffix.lower()

    # Check parent directory name
    if len(rel.parts) > 1:
        parent = rel.parts[0]
        if parent.lower() in ("guides", "guide"):
            return "Guides"
        if parent.lower() in ("controls", "controller", "controllers"):
            return "Controls"
        if parent.lower() in ("extra", "extras"):
            return "Extra"

    # Classify by extension
    for cat, exts in PAUSE_CATEGORIES.items():
        if ext in exts:
            if cat == "Guides" and ext in (".pdf", ".txt", ".zip", ".7z", ".rar"):
                return "Guides"
            if cat == "Controls" and ext in (".png", ".jpg", ".jpeg"):
                # Check filename hints
                name = filepath.stem.lower()
                if any(kw in name for kw in ("control", "button", "input", "pad", "key")):
                    return "Controls"
    return "Other"


# ── Full Coverage Report ─────────────────────────────────────────────

def media_coverage(
    rl_root: Optional[str] = None,
    systems: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Generate a full media coverage report across all or specified systems.

    Scans Fade, Bezels, and Pause directories for every system found
    in RL Settings and computes coverage percentages.

    Args:
        rl_root: RocketLauncher root path. Falls back to config.yaml.
        systems: Optional list of system names to scan. Scans all if None.

    Returns:
        Dict with per-system coverage and aggregate totals.
    """
    root = _get_rl_root(rl_root)
    report = RLMediaReport(rl_root=str(root))

    if not root.exists():
        report.issues.append(MediaIssue(
            severity=SEVERITY_ERROR,
            category="root",
            system="",
            message=f"RocketLauncher root not found: {root}",
        ))
        return report.to_dict()

    media_dir = root / "Media"
    if not media_dir.exists():
        report.issues.append(MediaIssue(
            severity=SEVERITY_ERROR,
            category="root",
            system="",
            message="Media directory not found in RocketLauncher root",
        ))
        return report.to_dict()

    # Discover systems from all media subdirectories
    if systems is None:
        system_names: set[str] = set()
        for media_type_dir in [media_dir / "Fade", media_dir / "Bezels", media_dir / "Pause"]:
            if media_type_dir.exists():
                for d in media_type_dir.iterdir():
                    if d.is_dir():
                        system_names.add(d.name)
        # Also check RL Settings for systems without media
        settings_dir = root / "Settings"
        if settings_dir.exists():
            for d in settings_dir.iterdir():
                if d.is_dir() and d.name.lower() not in ("global", "rocketlauncher", "_default"):
                    system_names.add(d.name)
        systems = sorted(system_names)

    for sys_name in systems:
        cov = SystemCoverage(system=sys_name)

        # Get ROM count for coverage calculation
        roms = _get_rom_list(root, sys_name)
        cov.game_count = len(roms)

        # Scan fades
        fade_result = scan_fade(sys_name, str(root))
        cov.fade_count = fade_result.get("asset_count", 0)
        cov.fade_layers = fade_result.get("layer_counts", {})
        fade_size = fade_result.get("total_size_bytes", 0)

        # Scan bezels
        bezel_result = scan_bezels(sys_name, str(root))
        cov.bezel_count = bezel_result.get("asset_count", 0)
        bezel_size = bezel_result.get("total_size_bytes", 0)

        # Scan pause
        pause_result = scan_pause(sys_name, str(root))
        cov.pause_count = pause_result.get("asset_count", 0)
        cats = pause_result.get("category_counts", {})
        cov.pause_guides = cats.get("Guides", 0)
        cov.pause_controls = cats.get("Controls", 0)
        pause_size = pause_result.get("total_size_bytes", 0)

        cov.total_size_bytes = fade_size + bezel_size + pause_size

        # Compute coverage percentages
        if cov.game_count > 0:
            cov.fade_coverage_pct = min(100.0, (cov.fade_count / cov.game_count) * 100)
            cov.bezel_coverage_pct = min(100.0, (cov.bezel_count / cov.game_count) * 100)
            cov.pause_coverage_pct = min(100.0, (cov.pause_count / cov.game_count) * 100)
        elif cov.fade_count > 0 or cov.bezel_count > 0 or cov.pause_count > 0:
            # Has assets but no ROM list — mark as having some coverage
            cov.fade_coverage_pct = 50.0 if cov.fade_count > 0 else 0.0
            cov.bezel_coverage_pct = 50.0 if cov.bezel_count > 0 else 0.0
            cov.pause_coverage_pct = 50.0 if cov.pause_count > 0 else 0.0

        # Collect issues
        for issue_dict in fade_result.get("issues", []):
            cov.issues.append(MediaIssue(**{k: issue_dict.get(k, "") for k in
                              ["severity", "category", "system", "message", "file", "suggestion"]}))
        for issue_dict in bezel_result.get("issues", []):
            cov.issues.append(MediaIssue(**{k: issue_dict.get(k, "") for k in
                              ["severity", "category", "system", "message", "file", "suggestion"]}))
        for issue_dict in pause_result.get("issues", []):
            cov.issues.append(MediaIssue(**{k: issue_dict.get(k, "") for k in
                              ["severity", "category", "system", "message", "file", "suggestion"]}))

        # Aggregate
        report.systems.append(cov)
        report.total_fade += cov.fade_count
        report.total_bezels += cov.bezel_count
        report.total_pause += cov.pause_count
        report.total_size_bytes += cov.total_size_bytes
        report.issues.extend(cov.issues)

    report.systems_scanned = len(systems)
    report.total_issues = len(report.issues)

    log.info(
        "RL media scan: %d systems, %d fades, %d bezels, %d pause, %d issues",
        report.systems_scanned, report.total_fade, report.total_bezels,
        report.total_pause, report.total_issues,
    )

    return report.to_dict()


# ── Per-System Detail Report ─────────────────────────────────────────

def system_media_detail(
    system: str,
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Get detailed media report for a single system.

    Includes all fade layers, bezel inventory with orientation,
    pause asset categories, and INI configuration status.
    """
    root = _get_rl_root(rl_root)
    result: dict[str, Any] = {
        "system": system,
        "rl_root": str(root),
    }

    # Scan all three media types
    result["fade"] = scan_fade(system, str(root))
    result["bezels"] = scan_bezels(system, str(root))
    result["pause"] = scan_pause(system, str(root))

    # Check system INI for media configuration
    sys_ini = root / "Settings" / system / f"{system}.ini"
    result["ini_exists"] = sys_ini.exists()
    result["ini_config"] = {}

    if sys_ini.exists():
        parser = _safe_read_ini(sys_ini)
        if parser:
            # Extract fade/bezel/pause settings
            for section in ["Fade", "Bezel", "Bezels", "Pause"]:
                if parser.has_section(section):
                    result["ini_config"][section] = dict(parser.items(section))

    # Summary
    result["summary"] = {
        "fade_count": result["fade"].get("asset_count", 0),
        "bezel_count": result["bezels"].get("asset_count", 0),
        "pause_count": result["pause"].get("asset_count", 0),
        "total_size_mb": round(
            (result["fade"].get("total_size_bytes", 0) +
             result["bezels"].get("total_size_bytes", 0) +
             result["pause"].get("total_size_bytes", 0)) / (1024 * 1024), 1
        ),
        "total_issues": (
            len(result["fade"].get("issues", [])) +
            len(result["bezels"].get("issues", [])) +
            len(result["pause"].get("issues", []))
        ),
    }

    return result


# ── Missing Asset Detection ──────────────────────────────────────────

def find_missing_media(
    system: str,
    media_type: str = "all",
    rl_root: Optional[str] = None,
) -> dict[str, Any]:
    """Find games that are missing specific media types.

    Cross-references ROM list against media directories to identify gaps.

    Args:
        system: System name to check.
        media_type: 'fade', 'bezels', 'pause', or 'all'.
        rl_root: RocketLauncher root path.

    Returns:
        Dict with lists of games missing each media type.
    """
    root = _get_rl_root(rl_root)
    result: dict[str, Any] = {"system": system, "rl_root": str(root)}

    roms = _get_rom_list(root, system)
    result["total_games"] = len(roms)

    if not roms:
        result["note"] = "No ROM list found — cannot determine missing media"
        return result

    rom_set = {r.lower() for r in roms}

    if media_type in ("fade", "all"):
        fade_dir = root / "Media" / "Fade" / system
        fade_games = set()
        if fade_dir.exists():
            for item in fade_dir.iterdir():
                if item.is_file() and item.suffix.lower() in VALID_IMAGE_EXTS:
                    fade_games.add(item.stem.lower())
                elif item.is_dir():
                    fade_games.add(item.name.lower())
        missing_fade = sorted(r for r in roms if r.lower() not in fade_games)
        result["missing_fade"] = missing_fade[:500]
        result["missing_fade_count"] = len(missing_fade)
        result["fade_coverage_pct"] = round(
            ((len(roms) - len(missing_fade)) / len(roms)) * 100, 1) if roms else 0

    if media_type in ("bezels", "all"):
        bezel_dir = root / "Media" / "Bezels" / system
        bezel_games = set()
        if bezel_dir.exists():
            for item in bezel_dir.iterdir():
                if item.is_file() and item.suffix.lower() in VALID_IMAGE_EXTS:
                    if "_background" not in item.stem.lower():
                        bezel_games.add(item.stem.lower())
                elif item.is_dir() and item.name.lower() != "backgrounds":
                    bezel_games.add(item.name.lower())
        missing_bezels = sorted(r for r in roms if r.lower() not in bezel_games)
        result["missing_bezels"] = missing_bezels[:500]
        result["missing_bezels_count"] = len(missing_bezels)
        result["bezel_coverage_pct"] = round(
            ((len(roms) - len(missing_bezels)) / len(roms)) * 100, 1) if roms else 0

    if media_type in ("pause", "all"):
        pause_dir = root / "Media" / "Pause" / system
        pause_games = set()
        if pause_dir.exists():
            for item in pause_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(pause_dir)
                    if len(rel.parts) > 1:
                        pause_games.add(rel.parts[0].lower())
                    else:
                        pause_games.add(item.stem.lower())
        missing_pause = sorted(r for r in roms if r.lower() not in pause_games)
        result["missing_pause"] = missing_pause[:500]
        result["missing_pause_count"] = len(missing_pause)
        result["pause_coverage_pct"] = round(
            ((len(roms) - len(missing_pause)) / len(roms)) * 100, 1) if roms else 0

    return result
