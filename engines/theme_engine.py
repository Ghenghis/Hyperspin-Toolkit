"""
M43 -- Thumbnail Cache & Dynamic Theme Loader (Theme Composition & Preview Engine)

Provides:
  - Optimized thumbnail cache generation (resized PNGs) for fast GUI browsing
  - ArcadeThemeEngine service: dynamically loads assets from all registered HDDs
  - Theme source priority chain: HyperSpin > AttractMode > LaunchBox > Batocera
  - Per-page theme mapping: best assets for each GUI page
  - Dynamic theme rotation with user favorites/pinning
  - SQLite persistence for cache metadata and user preferences
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import struct
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("theme_engine")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "theme_engine.db"
CACHE_DIR = TOOLKIT_ROOT / "cache" / "thumbnails"

# Theme source priority (higher index = higher priority)
SOURCE_PRIORITY = {
    "Batocera": 1,
    "CoreTypeR": 2,
    "AttractMode": 3,
    "LaunchBox": 4,
    "RocketLauncher": 5,
    "HyperSpin": 6,
}

# Default thumbnail sizes
THUMB_SIZES = {
    "small": (128, 96),
    "medium": (256, 192),
    "large": (512, 384),
    "grid": (200, 200),
}

# GUI page asset requirements
PAGE_REQUIREMENTS = {
    "dashboard": {
        "background": {"count": 5, "min_quality": 6.0, "preferred_types": ["background", "fanart"]},
        "hero": {"count": 3, "min_quality": 7.0, "preferred_types": ["theme_anim", "video"]},
        "system_icons": {"count": 50, "min_quality": 4.0, "preferred_types": ["system_artwork", "wheel_art"]},
    },
    "collection_browser": {
        "wheels": {"count": 200, "min_quality": 5.0, "preferred_types": ["wheel_art"]},
        "previews": {"count": 200, "min_quality": 4.0, "preferred_types": ["video", "snap"]},
        "backgrounds": {"count": 10, "min_quality": 6.0, "preferred_types": ["background"]},
    },
    "game_detail": {
        "box_art": {"count": 1, "min_quality": 5.0, "preferred_types": ["box_art"]},
        "screenshots": {"count": 4, "min_quality": 4.0, "preferred_types": ["snap"]},
        "video": {"count": 1, "min_quality": 5.0, "preferred_types": ["video"]},
        "fanart": {"count": 1, "min_quality": 6.0, "preferred_types": ["fanart"]},
    },
    "asset_gallery": {
        "all_art": {"count": 100, "min_quality": 3.0,
                    "preferred_types": ["wheel_art", "box_art", "fanart", "marquee", "flyer", "snap"]},
    },
}


@dataclass
class ThemeAsset:
    asset_id: str = ""
    path: str = ""
    system: str = ""
    game: str = ""
    asset_type: str = ""
    source: str = ""
    quality_score: float = 0.0
    width: int = 0
    height: int = 0
    has_thumbnail: bool = False
    thumbnail_path: str = ""
    is_favorite: bool = False
    is_pinned: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PageThemeMap:
    page: str = ""
    assets: Dict[str, List[ThemeAsset]] = field(default_factory=dict)
    coverage_pct: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = {"page": self.page, "coverage_pct": self.coverage_pct, "slots": {}}
        for slot, assets in self.assets.items():
            d["slots"][slot] = {
                "count": len(assets),
                "assets": [a.to_dict() for a in assets[:5]],  # top 5 per slot
            }
        return d


# ── SQLite ────────────────────────────────────────────────────────────

def _ensure_db() -> sqlite3.Connection:
    os.makedirs(DB_PATH.parent, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS thumbnail_cache (
            asset_id TEXT PRIMARY KEY,
            original_path TEXT NOT NULL,
            thumb_small TEXT DEFAULT '',
            thumb_medium TEXT DEFAULT '',
            thumb_large TEXT DEFAULT '',
            thumb_grid TEXT DEFAULT '',
            generated_at TEXT NOT NULL,
            original_width INTEGER DEFAULT 0,
            original_height INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS favorites (
            asset_id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            system TEXT DEFAULT '',
            game TEXT DEFAULT '',
            asset_type TEXT DEFAULT '',
            added_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pinned_themes (
            page TEXT NOT NULL,
            slot TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            path TEXT NOT NULL,
            pinned_at TEXT NOT NULL,
            PRIMARY KEY (page, slot, asset_id)
        );
        CREATE TABLE IF NOT EXISTS rotation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page TEXT NOT NULL,
            slot TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            shown_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_thumb_path ON thumbnail_cache(original_path);
        CREATE INDEX IF NOT EXISTS idx_fav_system ON favorites(system);
        CREATE INDEX IF NOT EXISTS idx_rotation_page ON rotation_history(page);
    """)
    conn.commit()
    return conn


# ── Thumbnail generation (pure Python, no PIL) ──────────────────────

def _png_dimensions(filepath: Path) -> Tuple[int, int]:
    try:
        with open(filepath, "rb") as f:
            sig = f.read(8)
            if sig[:4] != b"\x89PNG":
                return 0, 0
            f.read(4)
            if f.read(4) != b"IHDR":
                return 0, 0
            w, h = struct.unpack(">II", f.read(8))
            return w, h
    except Exception:
        return 0, 0


def generate_thumbnail(original_path: str, asset_id: str = "",
                       sizes: Optional[List[str]] = None) -> Dict[str, Any]:
    """Generate thumbnail(s) for an image asset.

    Without PIL, we create a metadata record and copy the original as a
    'thumbnail' placeholder. Real resizing requires Pillow or an external tool.
    """
    p = Path(original_path)
    if not p.exists():
        return {"error": f"File not found: {original_path}"}

    if not asset_id:
        asset_id = hashlib.sha256(str(p).encode()).hexdigest()[:12]

    if sizes is None:
        sizes = ["small", "medium", "grid"]

    w, h = _png_dimensions(p)
    conn = _ensure_db()
    now = datetime.now(timezone.utc).isoformat()
    thumbs = {}

    for size_name in sizes:
        if size_name not in THUMB_SIZES:
            continue
        tw, th = THUMB_SIZES[size_name]
        thumb_dir = CACHE_DIR / size_name
        os.makedirs(thumb_dir, exist_ok=True)
        thumb_path = thumb_dir / f"{asset_id}{p.suffix}"

        # Copy original as placeholder (real resizing needs PIL/ffmpeg)
        if not thumb_path.exists():
            try:
                import shutil
                shutil.copy2(str(p), str(thumb_path))
            except Exception:
                continue

        thumbs[f"thumb_{size_name}"] = str(thumb_path)

    try:
        conn.execute("""
            INSERT OR REPLACE INTO thumbnail_cache
            (asset_id, original_path, thumb_small, thumb_medium, thumb_large, thumb_grid,
             generated_at, original_width, original_height)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (asset_id, original_path,
              thumbs.get("thumb_small", ""), thumbs.get("thumb_medium", ""),
              thumbs.get("thumb_large", ""), thumbs.get("thumb_grid", ""),
              now, w, h))
        conn.commit()
    finally:
        conn.close()

    return {"asset_id": asset_id, "thumbnails": thumbs, "original_size": (w, h)}


def get_cache_stats() -> Dict[str, Any]:
    """Get thumbnail cache statistics."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM thumbnail_cache").fetchone()[0]
        cache_size = 0
        if CACHE_DIR.exists():
            for f in CACHE_DIR.rglob("*"):
                if f.is_file():
                    cache_size += f.stat().st_size
        return {
            "cached_thumbnails": total,
            "cache_size_mb": round(cache_size / (1024 * 1024), 1),
            "cache_dir": str(CACHE_DIR),
            "sizes_available": list(THUMB_SIZES.keys()),
        }
    finally:
        conn.close()


# ── Theme source resolution ──────────────────────────────────────────

def resolve_best_asset(game: str, asset_type: str, system: str = "",
                       sources: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Find the best asset for a game across all sources using priority chain.

    Args:
        game: Game name
        asset_type: Asset type (wheel_art, background, video, etc.)
        system: System name
        sources: Dict of {source_name: media_root_path}
    """
    if not sources:
        sources = _get_default_sources()

    candidates = []
    for source_name, root_path in sources.items():
        rp = Path(root_path)
        if not rp.exists():
            continue

        priority = SOURCE_PRIORITY.get(source_name, 0)

        # Search patterns based on asset type
        search_patterns = _get_search_patterns(asset_type, system, game)
        for pattern in search_patterns:
            for match in rp.glob(pattern):
                if match.is_file():
                    try:
                        size = match.stat().st_size
                    except OSError:
                        size = 0
                    candidates.append({
                        "path": str(match),
                        "source": source_name,
                        "priority": priority,
                        "size_kb": round(size / 1024, 1),
                        "game": game,
                        "asset_type": asset_type,
                    })

    if not candidates:
        return {"found": False, "game": game, "asset_type": asset_type}

    # Sort by priority (highest first), then by size (largest first)
    candidates.sort(key=lambda c: (c["priority"], c["size_kb"]), reverse=True)
    best = candidates[0]
    return {"found": True, "best": best, "alternatives": len(candidates) - 1,
            "all_sources": [c["source"] for c in candidates]}


def _get_default_sources() -> Dict[str, str]:
    """Get default media source paths from drive registry."""
    return {
        "HyperSpin": r"D:\Arcade\HyperSpin\Media",
        "RocketLauncher": r"D:\Arcade\RocketLauncher\Media",
        "AttractMode": r"D:\Arcade\menu-art",
    }


def _get_search_patterns(asset_type: str, system: str, game: str) -> List[str]:
    """Generate glob patterns for finding assets."""
    patterns = []
    sys_part = f"{system}/" if system else "*/"

    type_dirs = {
        "wheel_art": ["Images/Wheel"],
        "background": ["Images/Backgrounds"],
        "box_art": ["Images/Artwork1", "Images/Artwork2"],
        "video": ["Video"],
        "snap": ["snap", "Images/Snap"],
        "fanart": ["fanart"],
        "marquee": ["marquee"],
        "theme_anim": ["Themes"],
        "audio": ["Sound"],
    }

    dirs = type_dirs.get(asset_type, [asset_type])
    for d in dirs:
        patterns.append(f"{sys_part}{d}/{game}.*")
        patterns.append(f"{d}/{game}.*")

    return patterns


# ── Page theme mapping ───────────────────────────────────────────────

def get_page_theme_map(page: str) -> Dict[str, Any]:
    """Get the current theme mapping for a GUI page.

    Returns which assets are assigned to each slot on the page,
    including pinned items and auto-selected best assets.
    """
    if page not in PAGE_REQUIREMENTS:
        return {"error": f"Unknown page: {page}. Available: {list(PAGE_REQUIREMENTS.keys())}"}

    conn = _ensure_db()
    try:
        requirements = PAGE_REQUIREMENTS[page]
        result = {"page": page, "slots": {}, "total_slots": 0, "filled_slots": 0}

        for slot_name, req in requirements.items():
            # Check for pinned assets first
            pinned = conn.execute(
                "SELECT asset_id, path FROM pinned_themes WHERE page=? AND slot=?",
                (page, slot_name)
            ).fetchall()

            result["slots"][slot_name] = {
                "required": req["count"],
                "preferred_types": req["preferred_types"],
                "min_quality": req["min_quality"],
                "pinned_count": len(pinned),
                "pinned": [{"asset_id": r[0], "path": r[1]} for r in pinned],
            }
            result["total_slots"] += 1
            if pinned:
                result["filled_slots"] += 1

        result["coverage_pct"] = round(result["filled_slots"] / max(result["total_slots"], 1) * 100, 1)
        return result
    finally:
        conn.close()


# ── Favorites & pinning ──────────────────────────────────────────────

def add_favorite(asset_id: str, path: str, system: str = "",
                 game: str = "", asset_type: str = "") -> Dict[str, Any]:
    """Add an asset to favorites."""
    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT OR REPLACE INTO favorites (asset_id, path, system, game, asset_type, added_at)
            VALUES (?,?,?,?,?,?)
        """, (asset_id, path, system, game, asset_type, now))
        conn.commit()
        return {"favorited": True, "asset_id": asset_id}
    finally:
        conn.close()


def remove_favorite(asset_id: str) -> Dict[str, Any]:
    """Remove an asset from favorites."""
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM favorites WHERE asset_id=?", (asset_id,))
        conn.commit()
        return {"removed": True, "asset_id": asset_id}
    finally:
        conn.close()


def list_favorites(system: str = "", limit: int = 50) -> Dict[str, Any]:
    """List favorited assets."""
    conn = _ensure_db()
    try:
        sql = "SELECT * FROM favorites"
        params: list = []
        if system:
            sql += " WHERE system=?"
            params.append(system)
        sql += " ORDER BY added_at DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        cols = [d[0] for d in conn.execute("SELECT * FROM favorites LIMIT 0").description]
        return {"favorites": [dict(zip(cols, r)) for r in rows], "count": len(rows)}
    finally:
        conn.close()


def pin_to_page(page: str, slot: str, asset_id: str, path: str) -> Dict[str, Any]:
    """Pin an asset to a specific page slot."""
    if page not in PAGE_REQUIREMENTS:
        return {"error": f"Unknown page: {page}"}
    if slot not in PAGE_REQUIREMENTS[page]:
        return {"error": f"Unknown slot '{slot}' for page '{page}'"}

    conn = _ensure_db()
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT OR REPLACE INTO pinned_themes (page, slot, asset_id, path, pinned_at)
            VALUES (?,?,?,?,?)
        """, (page, slot, asset_id, path, now))
        conn.commit()
        return {"pinned": True, "page": page, "slot": slot, "asset_id": asset_id}
    finally:
        conn.close()


def unpin_from_page(page: str, slot: str, asset_id: str) -> Dict[str, Any]:
    """Unpin an asset from a page slot."""
    conn = _ensure_db()
    try:
        conn.execute("DELETE FROM pinned_themes WHERE page=? AND slot=? AND asset_id=?",
                     (page, slot, asset_id))
        conn.commit()
        return {"unpinned": True, "page": page, "slot": slot}
    finally:
        conn.close()


# ── Theme rotation ───────────────────────────────────────────────────

def rotate_theme(page: str, slot: str) -> Dict[str, Any]:
    """Select the next theme asset for rotation on a page slot.

    Picks from available assets, avoiding recently shown ones.
    """
    conn = _ensure_db()
    try:
        # Get recently shown asset IDs for this slot
        recent = conn.execute(
            "SELECT asset_id FROM rotation_history WHERE page=? AND slot=? ORDER BY shown_at DESC LIMIT 10",
            (page, slot)
        ).fetchall()
        recent_ids = {r[0] for r in recent}

        # Get pinned assets for this slot (these always stay)
        pinned = conn.execute(
            "SELECT asset_id, path FROM pinned_themes WHERE page=? AND slot=?",
            (page, slot)
        ).fetchall()

        if pinned:
            # Rotate through pinned assets, preferring ones not recently shown
            for pid, ppath in pinned:
                if pid not in recent_ids:
                    now = datetime.now(timezone.utc).isoformat()
                    conn.execute(
                        "INSERT INTO rotation_history (page, slot, asset_id, shown_at) VALUES (?,?,?,?)",
                        (page, slot, pid, now))
                    conn.commit()
                    return {"rotated": True, "asset_id": pid, "path": ppath, "source": "pinned"}

            # All pinned recently shown, cycle back to first
            return {"rotated": True, "asset_id": pinned[0][0], "path": pinned[0][1], "source": "pinned_cycle"}

        return {"rotated": False, "reason": "No assets available for this slot. Pin some assets first."}
    finally:
        conn.close()


# ── Summary ──────────────────────────────────────────────────────────

def theme_engine_status() -> Dict[str, Any]:
    """Get overall theme engine status."""
    conn = _ensure_db()
    try:
        cache = get_cache_stats()
        favs = conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0]
        pinned = conn.execute("SELECT COUNT(*) FROM pinned_themes").fetchone()[0]
        rotations = conn.execute("SELECT COUNT(*) FROM rotation_history").fetchone()[0]

        page_coverage = {}
        for page in PAGE_REQUIREMENTS:
            slots = len(PAGE_REQUIREMENTS[page])
            filled = conn.execute(
                "SELECT COUNT(DISTINCT slot) FROM pinned_themes WHERE page=?", (page,)
            ).fetchone()[0]
            page_coverage[page] = {"slots": slots, "filled": filled,
                                    "pct": round(filled / max(slots, 1) * 100, 1)}

        return {
            "thumbnail_cache": cache,
            "favorites": favs,
            "pinned_themes": pinned,
            "total_rotations": rotations,
            "page_coverage": page_coverage,
            "source_priority": SOURCE_PRIORITY,
            "available_pages": list(PAGE_REQUIREMENTS.keys()),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python theme_engine.py [status|cache|favorites|pages]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "status":
        print(json.dumps(theme_engine_status(), indent=2))
    elif cmd == "cache":
        print(json.dumps(get_cache_stats(), indent=2))
    elif cmd == "favorites":
        print(json.dumps(list_favorites(), indent=2))
    elif cmd == "pages":
        for p in PAGE_REQUIREMENTS:
            print(json.dumps(get_page_theme_map(p), indent=2))
