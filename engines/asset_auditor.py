"""Asset Auditor Engine — Scan gaming HDDs for visual, audio, and animation assets.

Indexes all game assets across registered drives, calculates quality scores,
and builds a searchable catalog for the Arcade GUI theme engine and agent-driven curation.

Supports:
  - HyperSpin Media structure (Images/Wheel, Backgrounds, Artwork, Themes, Video, Sound)
  - Attract Mode menu-art (fanart, flyer, marquee, snap, themes)
  - CORE - TYPE R (system_artwork, menu)
  - Batocera (themes, decorations, splash)

Usage:
  from engines.asset_auditor import AssetAuditor
  auditor = AssetAuditor(registry_path="drive_registry.json")
  results = auditor.scan_drive("D")
  auditor.save_index("asset_index.json")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("asset_auditor")

# ---------------------------------------------------------------------------
# Asset type definitions
# ---------------------------------------------------------------------------

ASSET_TYPES = {
    "wheel_art": {
        "patterns": ["Images/Wheel", "Images\\Wheel"],
        "extensions": {".png", ".jpg", ".jpeg", ".gif"},
        "description": "Circular game logo art for wheel navigation",
    },
    "background": {
        "patterns": ["Images/Backgrounds", "Images\\Backgrounds"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "System or game background images",
    },
    "box_art": {
        "patterns": ["Images/Artwork1", "Images/Artwork2", "Images/Artwork3", "Images/Artwork4",
                      "Images\\Artwork1", "Images\\Artwork2", "Images\\Artwork3", "Images\\Artwork4"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "Box art, screenshots, or promotional art layers",
    },
    "genre_icon": {
        "patterns": ["Images/Genre", "Images\\Genre"],
        "extensions": {".png"},
        "description": "Genre classification icons",
    },
    "special_art": {
        "patterns": ["Images/Special", "Images\\Special"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "Special promotional or collector art",
    },
    "letter_art": {
        "patterns": ["Images/Letters", "Images\\Letters"],
        "extensions": {".png"},
        "description": "Alphabetical letter art for navigation",
    },
    "theme_anim": {
        "patterns": ["Themes"],
        "extensions": {".swf", ".zip"},
        "description": "Animated themes (Flash SWF or zipped assets)",
    },
    "video": {
        "patterns": ["Video"],
        "extensions": {".mp4", ".flv", ".avi", ".mkv", ".wmv"},
        "description": "Game preview or attract-mode videos",
    },
    "audio": {
        "patterns": ["Sound"],
        "extensions": {".mp3", ".wav", ".ogg", ".flac"},
        "description": "Game music, sound effects, or narration",
    },
    "fanart": {
        "patterns": ["fanart"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "Fan-created artwork",
    },
    "marquee": {
        "patterns": ["marquee"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "Arcade cabinet marquee images",
    },
    "flyer": {
        "patterns": ["flyer"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "Original game flyer scans",
    },
    "snap": {
        "patterns": ["snap"],
        "extensions": {".png", ".jpg", ".jpeg"},
        "description": "In-game screenshots",
    },
    "bezel": {
        "patterns": ["decorations", "bezels", "overlays"],
        "extensions": {".png", ".cfg", ".lay"},
        "description": "Screen bezels and overlays",
    },
    "system_artwork": {
        "patterns": ["system_artwork"],
        "extensions": {".png", ".jpg", ".jpeg", ".svg"},
        "description": "System-level artwork (console logos, etc.)",
    },
}

# GUI page recommendations for asset types
PAGE_ASSET_MAP = {
    "dashboard": ["background", "video", "theme_anim", "system_artwork"],
    "collection_browser": ["wheel_art", "video", "box_art", "background", "audio"],
    "drive_manager": ["system_artwork", "background"],
    "agent_console": ["background"],
    "asset_gallery": ["wheel_art", "box_art", "fanart", "marquee", "flyer", "snap"],
    "update_center": ["background", "system_artwork"],
    "rom_audit": ["wheel_art", "genre_icon"],
    "backup_control": ["background"],
    "settings": ["background", "letter_art"],
    "ai_chat": ["background", "theme_anim"],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AssetRecord:
    """Single indexed asset."""
    asset_id: str = ""
    path: str = ""
    drive_letter: str = ""
    drive_tag: str = ""
    system: str = ""
    game: str = ""
    asset_type: str = ""
    format: str = ""
    width: int = 0
    height: int = 0
    file_size_kb: float = 0.0
    quality_score: float = 0.0
    gui_usable: bool = True
    recommended_for: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanStats:
    """Aggregated scan statistics."""
    total_assets: int = 0
    total_size_mb: float = 0.0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_format: Dict[str, int] = field(default_factory=dict)
    by_system: Dict[str, int] = field(default_factory=dict)
    by_drive: Dict[str, int] = field(default_factory=dict)
    scan_duration_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helper: read PNG dimensions without PIL
# ---------------------------------------------------------------------------

def _png_dimensions(filepath: Path) -> Tuple[int, int]:
    """Read width/height from a PNG header (IHDR chunk)."""
    try:
        with open(filepath, "rb") as f:
            sig = f.read(8)
            if sig[:4] != b"\x89PNG":
                return 0, 0
            # Skip chunk length (4) and chunk type (4) = IHDR
            f.read(4)  # chunk length
            chunk_type = f.read(4)
            if chunk_type != b"IHDR":
                return 0, 0
            w, h = struct.unpack(">II", f.read(8))
            return w, h
    except Exception:
        return 0, 0


def _jpg_dimensions(filepath: Path) -> Tuple[int, int]:
    """Read width/height from JPEG SOF marker."""
    try:
        with open(filepath, "rb") as f:
            data = f.read(32768)  # Read first 32KB
            i = 0
            if data[0:2] != b"\xff\xd8":
                return 0, 0
            i = 2
            while i < len(data) - 8:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h = struct.unpack(">H", data[i + 5 : i + 7])[0]
                    w = struct.unpack(">H", data[i + 7 : i + 9])[0]
                    return w, h
                length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return 0, 0


def get_image_dimensions(filepath: Path) -> Tuple[int, int]:
    """Get image dimensions without external dependencies."""
    ext = filepath.suffix.lower()
    if ext == ".png":
        return _png_dimensions(filepath)
    elif ext in (".jpg", ".jpeg"):
        return _jpg_dimensions(filepath)
    return 0, 0


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def compute_quality_score(record: AssetRecord) -> float:
    """Compute a 0-10 quality score for an asset based on available metrics."""
    score = 5.0  # baseline

    # Resolution bonus (for images)
    if record.width > 0 and record.height > 0:
        pixels = record.width * record.height
        if pixels >= 1920 * 1080:
            score += 2.0
        elif pixels >= 1280 * 720:
            score += 1.5
        elif pixels >= 640 * 480:
            score += 0.5
        elif pixels < 200 * 200:
            score -= 1.0

    # File size heuristic (larger = likely higher quality for images)
    if record.asset_type in ("wheel_art", "background", "box_art", "fanart", "marquee"):
        if record.file_size_kb > 500:
            score += 1.0
        elif record.file_size_kb > 100:
            score += 0.5
        elif record.file_size_kb < 10:
            score -= 1.0

    # Animated themes and videos get a bonus
    if record.asset_type == "theme_anim":
        score += 1.5
    if record.asset_type == "video":
        if record.file_size_kb > 5000:
            score += 1.5  # Longer/higher quality video
        elif record.file_size_kb > 1000:
            score += 1.0

    # PNG preferred over JPG for wheel art and backgrounds
    if record.format == ".png" and record.asset_type in ("wheel_art", "background"):
        score += 0.5

    return max(0.0, min(10.0, round(score, 1)))


# ---------------------------------------------------------------------------
# Asset type detection
# ---------------------------------------------------------------------------

def classify_asset(filepath: Path, base_media_dir: Path) -> Optional[str]:
    """Determine the asset type from the file path relative to the media directory."""
    try:
        rel = filepath.relative_to(base_media_dir)
    except ValueError:
        return None

    rel_str = str(rel)
    ext = filepath.suffix.lower()

    for asset_type, info in ASSET_TYPES.items():
        if ext not in info["extensions"]:
            continue
        for pattern in info["patterns"]:
            if pattern.lower() in rel_str.lower():
                return asset_type
    return None


def extract_system_game(filepath: Path, base_media_dir: Path) -> Tuple[str, str]:
    """Extract system name and game name from path structure.

    Expected structures:
      Media/{System}/Images/Wheel/{game}.png  → system="System", game="game"
      Media/{System}/Video/{game}.mp4         → system="System", game="game"
      menu-art/fanart/{game}.png              → system="", game="game"
    """
    try:
        rel = filepath.relative_to(base_media_dir)
    except ValueError:
        return "", filepath.stem

    parts = rel.parts
    if len(parts) >= 2:
        system = parts[0]
        game = filepath.stem
        return system, game
    return "", filepath.stem


# ---------------------------------------------------------------------------
# Main Auditor class
# ---------------------------------------------------------------------------

class AssetAuditor:
    """Scans gaming HDDs and builds a searchable asset index."""

    def __init__(self, registry_path: str = "drive_registry.json"):
        self.registry_path = registry_path
        self.registry: dict = {}
        self.assets: List[AssetRecord] = []
        self.stats = ScanStats()
        self._load_registry()

    def _load_registry(self):
        """Load drive registry for tag resolution."""
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                self.registry = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.registry = {"drives": [], "system_drives": []}

    def _resolve_drive_tag(self, drive_letter: str) -> str:
        """Look up the drive tag from the registry."""
        letter = drive_letter.upper().rstrip(":")
        for d in self.registry.get("drives", []):
            if d.get("current_letter", "").upper() == letter:
                return d.get("tag", "UNKNOWN")
        for d in self.registry.get("system_drives", []):
            if d.get("current_letter", "").upper() == letter:
                return d.get("tag", "UNKNOWN")
        return "UNKNOWN"

    # ----- Scan Paths -----

    def get_media_paths(self, drive_letter: str) -> List[Tuple[Path, str]]:
        """Return (path, source_label) tuples for known media locations on a drive."""
        root = Path(f"{drive_letter.upper().rstrip(':')}:\\")
        paths = []

        # HyperSpin Media
        hs_media = root / "Arcade" / "Media"
        if hs_media.exists():
            paths.append((hs_media, "HyperSpin"))

        # RocketLauncher Media
        rl_media = root / "Arcade" / "RocketLauncher" / "Media"
        if rl_media.exists():
            paths.append((rl_media, "RocketLauncher"))

        # Attract Mode menu-art
        am_art = root / "Arcade" / "menu-art"
        if am_art.exists():
            paths.append((am_art, "AttractMode"))

        # CORE - TYPE R
        ctr_art = root / "CORE - TYPE R" / "collections" / "Main" / "system_artwork"
        if ctr_art.exists():
            paths.append((ctr_art, "CoreTypeR"))
        ctr_menu = root / "CORE - TYPE R" / "collections" / "Main" / "menu"
        if ctr_menu.exists():
            paths.append((ctr_menu, "CoreTypeR"))

        # Batocera
        bat_themes = root / "themes"
        if bat_themes.exists():
            paths.append((bat_themes, "Batocera"))
        bat_deco = root / "decorations"
        if bat_deco.exists():
            paths.append((bat_deco, "Batocera"))

        # Direct Media folder at root
        direct_media = root / "Media"
        if direct_media.exists() and direct_media != hs_media:
            paths.append((direct_media, "DirectMedia"))

        return paths

    # ----- Scanning -----

    def scan_directory(self, media_dir: Path, drive_letter: str, source_label: str,
                       max_files: int = 0) -> List[AssetRecord]:
        """Scan a single media directory and return asset records."""
        drive_tag = self._resolve_drive_tag(drive_letter)
        records = []
        count = 0

        for root_dir, _dirs, files in os.walk(media_dir):
            for fname in files:
                filepath = Path(root_dir) / fname
                ext = filepath.suffix.lower()

                # Quick extension filter
                all_extensions = set()
                for info in ASSET_TYPES.values():
                    all_extensions.update(info["extensions"])
                if ext not in all_extensions:
                    continue

                asset_type = classify_asset(filepath, media_dir)
                if not asset_type:
                    # Fallback: classify by extension alone
                    if ext in (".png", ".jpg", ".jpeg"):
                        asset_type = "background"
                    elif ext in (".mp4", ".flv", ".avi"):
                        asset_type = "video"
                    elif ext in (".mp3", ".wav", ".ogg"):
                        asset_type = "audio"
                    elif ext in (".swf", ".zip"):
                        asset_type = "theme_anim"
                    else:
                        continue

                system, game = extract_system_game(filepath, media_dir)

                try:
                    fsize = filepath.stat().st_size
                except OSError:
                    fsize = 0

                w, h = 0, 0
                if asset_type in ("wheel_art", "background", "box_art", "genre_icon",
                                  "special_art", "letter_art", "fanart", "marquee",
                                  "flyer", "snap", "system_artwork"):
                    w, h = get_image_dimensions(filepath)

                # Generate short hash ID
                hash_input = str(filepath).encode("utf-8", errors="replace")
                asset_id = hashlib.sha256(hash_input).hexdigest()[:12]

                # Determine GUI page recommendations
                recommended = []
                for page, types in PAGE_ASSET_MAP.items():
                    if asset_type in types:
                        recommended.append(page)

                record = AssetRecord(
                    asset_id=asset_id,
                    path=str(filepath),
                    drive_letter=drive_letter.upper().rstrip(":"),
                    drive_tag=drive_tag,
                    system=system,
                    game=game,
                    asset_type=asset_type,
                    format=ext,
                    width=w,
                    height=h,
                    file_size_kb=round(fsize / 1024, 1),
                    recommended_for=recommended,
                )
                record.quality_score = compute_quality_score(record)
                record.gui_usable = record.quality_score >= 3.0

                records.append(record)
                count += 1

                if max_files > 0 and count >= max_files:
                    return records

        return records

    def scan_drive(self, drive_letter: str, max_files_per_dir: int = 0) -> List[AssetRecord]:
        """Scan all known media paths on a drive."""
        media_paths = self.get_media_paths(drive_letter)
        if not media_paths:
            logger.warning(f"No known media paths found on {drive_letter}:")
            return []

        drive_records = []
        for media_dir, source_label in media_paths:
            logger.info(f"Scanning {media_dir} ({source_label})...")
            records = self.scan_directory(media_dir, drive_letter, source_label,
                                          max_files=max_files_per_dir)
            drive_records.extend(records)
            logger.info(f"  Found {len(records)} assets in {source_label}")

        self.assets.extend(drive_records)
        return drive_records

    def scan_all_drives(self, drive_letters: Optional[List[str]] = None,
                        max_files_per_dir: int = 0) -> List[AssetRecord]:
        """Scan all registered gaming drives (or a specific list)."""
        if drive_letters is None:
            drive_letters = []
            for d in self.registry.get("drives", []):
                letter = d.get("current_letter", "")
                if letter:
                    drive_letters.append(letter)

        start = time.time()
        all_records = []
        for letter in drive_letters:
            records = self.scan_drive(letter, max_files_per_dir=max_files_per_dir)
            all_records.extend(records)

        self.stats = self._compute_stats(all_records, time.time() - start)
        return all_records

    # ----- Statistics -----

    def _compute_stats(self, records: List[AssetRecord], duration: float) -> ScanStats:
        """Compute aggregated statistics from scan results."""
        stats = ScanStats(scan_duration_sec=round(duration, 2))
        stats.total_assets = len(records)

        for r in records:
            stats.total_size_mb += r.file_size_kb / 1024
            stats.by_type[r.asset_type] = stats.by_type.get(r.asset_type, 0) + 1
            stats.by_format[r.format] = stats.by_format.get(r.format, 0) + 1
            if r.system:
                stats.by_system[r.system] = stats.by_system.get(r.system, 0) + 1
            stats.by_drive[r.drive_letter] = stats.by_drive.get(r.drive_letter, 0) + 1

        stats.total_size_mb = round(stats.total_size_mb, 1)
        return stats

    def get_stats(self) -> ScanStats:
        """Return current scan statistics (recompute if needed)."""
        if self.stats.total_assets == 0 and self.assets:
            self.stats = self._compute_stats(self.assets, 0)
        return self.stats

    # ----- Queries -----

    def query(self, asset_type: Optional[str] = None,
              system: Optional[str] = None,
              drive_letter: Optional[str] = None,
              min_quality: float = 0.0,
              min_width: int = 0,
              min_height: int = 0,
              format_filter: Optional[str] = None,
              gui_page: Optional[str] = None,
              limit: int = 100) -> List[AssetRecord]:
        """Query the asset index with filters."""
        results = self.assets

        if asset_type:
            results = [r for r in results if r.asset_type == asset_type]
        if system:
            results = [r for r in results if r.system.lower() == system.lower()]
        if drive_letter:
            dl = drive_letter.upper().rstrip(":")
            results = [r for r in results if r.drive_letter == dl]
        if min_quality > 0:
            results = [r for r in results if r.quality_score >= min_quality]
        if min_width > 0:
            results = [r for r in results if r.width >= min_width]
        if min_height > 0:
            results = [r for r in results if r.height >= min_height]
        if format_filter:
            fmt = format_filter if format_filter.startswith(".") else f".{format_filter}"
            results = [r for r in results if r.format == fmt]
        if gui_page:
            results = [r for r in results if gui_page in r.recommended_for]

        # Sort by quality score descending
        results.sort(key=lambda r: r.quality_score, reverse=True)
        return results[:limit]

    def best_assets_for_page(self, page: str, limit: int = 10) -> List[AssetRecord]:
        """Get the highest-quality assets recommended for a specific GUI page."""
        return self.query(gui_page=page, min_quality=5.0, limit=limit)

    def missing_media_report(self) -> Dict[str, List[str]]:
        """Find systems that have some asset types but are missing others.

        Returns a dict of {system: [missing_asset_types]}.
        """
        system_types: Dict[str, set] = {}
        for r in self.assets:
            if r.system:
                if r.system not in system_types:
                    system_types[r.system] = set()
                system_types[r.system].add(r.asset_type)

        expected = {"wheel_art", "background", "video", "audio"}
        report = {}
        for system, types in system_types.items():
            missing = expected - types
            if missing:
                report[system] = sorted(missing)
        return report

    def duplicate_assets(self) -> List[Tuple[str, List[str]]]:
        """Find duplicate assets (same game + type but on different drives)."""
        key_map: Dict[str, List[str]] = {}
        for r in self.assets:
            key = f"{r.system}|{r.game}|{r.asset_type}"
            if key not in key_map:
                key_map[key] = []
            key_map[key].append(r.path)

        return [(k, paths) for k, paths in key_map.items() if len(paths) > 1]

    # ----- Persistence -----

    def save_index(self, output_path: str = "asset_index.json"):
        """Save the asset index to a JSON file."""
        data = {
            "_generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "_stats": self.get_stats().to_dict(),
            "assets": [r.to_dict() for r in self.assets],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.assets)} assets to {output_path}")

    def load_index(self, input_path: str = "asset_index.json"):
        """Load a previously saved asset index."""
        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load index: {e}")
            return

        self.assets = []
        for item in data.get("assets", []):
            record = AssetRecord(**{
                k: v for k, v in item.items()
                if k in AssetRecord.__dataclass_fields__
            })
            self.assets.append(record)
        logger.info(f"Loaded {len(self.assets)} assets from {input_path}")

    # ----- Summary -----

    def summary(self) -> dict:
        """Generate a human-readable summary of the asset index."""
        stats = self.get_stats()
        top_systems = sorted(stats.by_system.items(), key=lambda x: x[1], reverse=True)[:10]
        missing = self.missing_media_report()

        return {
            "total_assets": stats.total_assets,
            "total_size_mb": stats.total_size_mb,
            "by_type": stats.by_type,
            "by_format": stats.by_format,
            "by_drive": stats.by_drive,
            "top_systems": dict(top_systems),
            "systems_with_missing_media": len(missing),
            "scan_duration_sec": stats.scan_duration_sec,
        }
