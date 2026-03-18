"""
M18 -- AI Game Recommendation Engine

Provides:
  - Collection analysis and game similarity scoring
  - "If you like X, try Y" recommendations
  - Hidden gem discovery from existing collection
  - Genre/era/style clustering
  - Tag-based and metadata-based matching
  - Cross-system recommendations
  - Popularity-weighted suggestions
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("game_recommender")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "game_metadata.db"


# -----------------------------------------------------------------------
# Genre / tag taxonomy
# -----------------------------------------------------------------------

GENRE_TAXONOMY: Dict[str, List[str]] = {
    "action": ["action", "beat em up", "beat-em-up", "hack and slash", "hack-and-slash"],
    "platformer": ["platformer", "platform", "side-scroller", "sidescroller"],
    "rpg": ["rpg", "role-playing", "role playing", "jrpg", "action rpg", "tactical rpg", "strategy rpg"],
    "fighting": ["fighting", "fighter", "versus", "vs", "1-on-1"],
    "shooter": ["shooter", "shmup", "shoot-em-up", "shoot em up", "run and gun", "fps", "tps"],
    "racing": ["racing", "driving", "kart", "rally"],
    "sports": ["sports", "football", "soccer", "baseball", "basketball", "tennis", "golf", "hockey"],
    "puzzle": ["puzzle", "tetris", "match", "brain", "logic"],
    "adventure": ["adventure", "point and click", "point-and-click", "graphic adventure"],
    "strategy": ["strategy", "rts", "turn-based", "turn based", "tactics", "4x", "simulation"],
    "simulation": ["simulation", "sim", "management", "tycoon", "city builder"],
    "horror": ["horror", "survival horror", "scary"],
    "stealth": ["stealth", "sneaking"],
    "music": ["music", "rhythm", "dance"],
    "educational": ["educational", "edutainment"],
    "pinball": ["pinball"],
    "casino": ["casino", "card", "board game"],
    "arcade": ["arcade", "classic arcade"],
}

ERA_RANGES = {
    "retro_early": (1970, 1984),
    "retro_golden": (1985, 1992),
    "16bit_era": (1993, 1996),
    "3d_revolution": (1997, 2001),
    "modern_classic": (2002, 2010),
    "modern": (2011, 2025),
}

SYSTEM_GENERATIONS: Dict[str, str] = {
    "Atari 2600": "retro_early", "Atari 5200": "retro_early",
    "ColecoVision": "retro_early", "Intellivision": "retro_early",
    "NES": "retro_golden", "Master System": "retro_golden",
    "Game Boy": "retro_golden", "Atari 7800": "retro_golden",
    "SNES": "16bit_era", "Genesis": "16bit_era", "Mega Drive": "16bit_era",
    "TurboGrafx-16": "16bit_era", "Neo Geo": "16bit_era",
    "Game Boy Color": "16bit_era", "Game Gear": "16bit_era",
    "Sega CD": "16bit_era", "Atari Lynx": "16bit_era",
    "PlayStation": "3d_revolution", "N64": "3d_revolution",
    "Saturn": "3d_revolution", "Dreamcast": "3d_revolution",
    "GBA": "3d_revolution", "WonderSwan": "3d_revolution",
    "PS2": "modern_classic", "GameCube": "modern_classic",
    "Xbox": "modern_classic", "NDS": "modern_classic",
    "PSP": "modern_classic", "Wii": "modern_classic",
    "3DO": "3d_revolution", "Jaguar": "3d_revolution",
    "Arcade": "retro_golden", "MAME": "retro_golden",
}


# -----------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------

@dataclass
class GameProfile:
    """Profile of a game for recommendation matching."""
    name: str
    system: str
    genre: str = ""
    year: str = ""
    developer: str = ""
    publisher: str = ""
    rating: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    era: str = ""
    normalized_genres: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Recommendation:
    """A game recommendation with scoring."""
    game_name: str
    system: str
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)
    genre: str = ""
    year: str = ""
    developer: str = ""
    rating: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# Genre normalization
# -----------------------------------------------------------------------

def normalize_genre(genre_str: str) -> List[str]:
    """Normalize a genre string into canonical genre tags."""
    if not genre_str:
        return []
    lower = genre_str.lower()
    found = []
    for canonical, variants in GENRE_TAXONOMY.items():
        for v in variants:
            if v in lower:
                found.append(canonical)
                break
    return list(set(found)) or ["unknown"]


def classify_era(year_str: str, system: str = "") -> str:
    """Classify a game into an era based on year or system."""
    if year_str:
        try:
            year = int(year_str[:4])
            for era, (start, end) in ERA_RANGES.items():
                if start <= year <= end:
                    return era
        except (ValueError, IndexError):
            pass
    return SYSTEM_GENERATIONS.get(system, "unknown")


# -----------------------------------------------------------------------
# Collection analysis
# -----------------------------------------------------------------------

def _load_collection() -> List[GameProfile]:
    """Load game profiles from the metadata database."""
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT game_name, system, genre, year, developer, publisher, rating, description "
            "FROM game_metadata ORDER BY game_name"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()

    profiles = []
    for r in rows:
        genres = normalize_genre(r[2])
        era = classify_era(r[3], r[1])
        profiles.append(GameProfile(
            name=r[0], system=r[1], genre=r[2], year=r[3],
            developer=r[4] or "", publisher=r[5] or "",
            rating=r[6] or "", description=r[7] or "",
            normalized_genres=genres, era=era,
        ))
    return profiles


def _load_rom_names(system: str = "") -> List[Dict[str, str]]:
    """Load ROM names from the ROM audit database if available."""
    rom_db = TOOLKIT_ROOT / "data" / "rom_audit.db"
    if not rom_db.exists():
        return []
    conn = sqlite3.connect(str(rom_db))
    try:
        if system:
            rows = conn.execute(
                "SELECT DISTINCT game_name, system FROM rom_files WHERE system=?",
                (system,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT DISTINCT game_name, system FROM rom_files"
            ).fetchall()
        return [{"name": r[0], "system": r[1]} for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def analyze_collection(system: str = "") -> Dict[str, Any]:
    """Analyze the user's game collection for patterns and preferences.

    Returns genre distribution, era breakdown, top developers, and
    preference profile used for recommendations.
    """
    profiles = _load_collection()
    if system:
        profiles = [p for p in profiles if p.system == system]

    if not profiles:
        return {
            "total_games": 0,
            "message": "No metadata found. Run scrape_game_metadata first.",
        }

    genre_counts: Counter = Counter()
    era_counts: Counter = Counter()
    dev_counts: Counter = Counter()
    pub_counts: Counter = Counter()
    system_counts: Counter = Counter()
    ratings: List[float] = []

    for p in profiles:
        for g in p.normalized_genres:
            genre_counts[g] += 1
        era_counts[p.era] += 1
        system_counts[p.system] += 1
        if p.developer:
            dev_counts[p.developer] += 1
        if p.publisher:
            pub_counts[p.publisher] += 1
        try:
            r = float(p.rating)
            if r > 0:
                ratings.append(r)
        except (ValueError, TypeError):
            pass

    return {
        "total_games": len(profiles),
        "genre_distribution": dict(genre_counts.most_common(15)),
        "era_distribution": dict(era_counts.most_common()),
        "system_distribution": dict(system_counts.most_common(20)),
        "top_developers": dict(dev_counts.most_common(10)),
        "top_publishers": dict(pub_counts.most_common(10)),
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else 0,
        "preference_profile": {
            "favorite_genres": [g for g, _ in genre_counts.most_common(3)],
            "favorite_era": era_counts.most_common(1)[0][0] if era_counts else "unknown",
            "favorite_developers": [d for d, _ in dev_counts.most_common(3)],
        },
    }


# -----------------------------------------------------------------------
# Similarity scoring
# -----------------------------------------------------------------------

def _compute_similarity(source: GameProfile, candidate: GameProfile) -> Tuple[float, List[str]]:
    """Compute similarity score between two games."""
    score = 0.0
    reasons = []

    # Genre match (highest weight)
    src_genres = set(source.normalized_genres)
    cand_genres = set(candidate.normalized_genres)
    genre_overlap = src_genres & cand_genres
    if genre_overlap:
        genre_score = len(genre_overlap) / max(len(src_genres), 1) * 40
        score += genre_score
        reasons.append(f"Same genre: {', '.join(genre_overlap)}")

    # Era match
    if source.era and source.era == candidate.era:
        score += 15
        reasons.append(f"Same era: {source.era}")

    # Developer match
    if source.developer and source.developer == candidate.developer:
        score += 20
        reasons.append(f"Same developer: {source.developer}")

    # Publisher match
    if source.publisher and source.publisher == candidate.publisher:
        score += 5
        reasons.append(f"Same publisher: {source.publisher}")

    # System match (slight bonus for same system)
    if source.system == candidate.system:
        score += 5
        reasons.append(f"Same system: {source.system}")

    # Rating bonus (prefer higher-rated games)
    try:
        rating = float(candidate.rating)
        if rating > 70:
            bonus = (rating - 70) / 30 * 10  # 0-10 bonus for 70-100 rated
            score += bonus
            reasons.append(f"Highly rated: {rating:.0f}")
    except (ValueError, TypeError):
        pass

    # Name similarity (detect series)
    src_base = re.sub(r'\s*[\(\[].*?[\)\]]|\s*[IVX]+$|\s*\d+$', '', source.name).strip().lower()
    cand_base = re.sub(r'\s*[\(\[].*?[\)\]]|\s*[IVX]+$|\s*\d+$', '', candidate.name).strip().lower()
    if src_base and cand_base and src_base in cand_base or cand_base in src_base:
        if source.name != candidate.name:
            score += 15
            reasons.append("Same series")

    return score, reasons


# -----------------------------------------------------------------------
# Recommendation engine
# -----------------------------------------------------------------------

def recommend_similar(game_name: str, system: str = "",
                      limit: int = 10, cross_system: bool = True) -> Dict[str, Any]:
    """Get games similar to a given game.

    Args:
        game_name: Source game name
        system: System of the source game (optional)
        limit: Max recommendations
        cross_system: Include games from other systems

    Returns:
        List of recommendations with scores and reasons
    """
    profiles = _load_collection()
    if not profiles:
        return {"error": "No metadata in database. Run scrape_game_metadata first."}

    # Find the source game
    source = None
    for p in profiles:
        if p.name.lower() == game_name.lower():
            if not system or p.system == system:
                source = p
                break

    if not source:
        # Try fuzzy match
        for p in profiles:
            if game_name.lower() in p.name.lower():
                if not system or p.system == system:
                    source = p
                    break

    if not source:
        return {"error": f"Game '{game_name}' not found in metadata database"}

    # Score all candidates
    candidates = []
    for p in profiles:
        if p.name == source.name and p.system == source.system:
            continue
        if not cross_system and p.system != source.system:
            continue

        score, reasons = _compute_similarity(source, p)
        if score > 10:  # Minimum threshold
            candidates.append(Recommendation(
                game_name=p.name, system=p.system, score=round(score, 1),
                reasons=reasons, genre=p.genre, year=p.year,
                developer=p.developer, rating=p.rating,
            ))

    candidates.sort(key=lambda r: r.score, reverse=True)
    top = candidates[:limit]

    return {
        "source_game": source.name,
        "source_system": source.system,
        "source_genre": source.genre,
        "recommendations": [r.to_dict() for r in top],
        "total_candidates": len(candidates),
    }


def recommend_by_preference(system: str = "", genres: List[str] = None,
                            era: str = "", developer: str = "",
                            limit: int = 15) -> Dict[str, Any]:
    """Get recommendations based on preference criteria.

    Args:
        system: Filter to a specific system
        genres: Preferred genres
        era: Preferred era
        developer: Preferred developer
        limit: Max recommendations

    Returns:
        Matching games ranked by preference score
    """
    profiles = _load_collection()
    if not profiles:
        return {"error": "No metadata in database. Run scrape_game_metadata first."}

    if system:
        profiles = [p for p in profiles if p.system == system]

    candidates = []
    for p in profiles:
        score = 0.0
        reasons = []

        if genres:
            overlap = set(normalize_genre(g) for g in genres if g) & set(p.normalized_genres)
            flat_overlap = set()
            for item in overlap:
                if isinstance(item, (list, tuple)):
                    flat_overlap.update(item)
                else:
                    flat_overlap.add(item)
            genre_match = flat_overlap & set(p.normalized_genres)
            if genre_match:
                score += len(genre_match) * 25
                reasons.append(f"Matches genre: {', '.join(genre_match)}")

        if era and p.era == era:
            score += 20
            reasons.append(f"Era: {era}")

        if developer and p.developer and developer.lower() in p.developer.lower():
            score += 30
            reasons.append(f"Developer: {p.developer}")

        try:
            r = float(p.rating)
            if r > 70:
                score += (r - 70) / 30 * 15
                reasons.append(f"Rating: {r:.0f}")
        except (ValueError, TypeError):
            pass

        if score > 5:
            candidates.append(Recommendation(
                game_name=p.name, system=p.system, score=round(score, 1),
                reasons=reasons, genre=p.genre, year=p.year,
                developer=p.developer, rating=p.rating,
            ))

    candidates.sort(key=lambda r: r.score, reverse=True)
    top = candidates[:limit]

    return {
        "criteria": {
            "system": system, "genres": genres, "era": era, "developer": developer,
        },
        "recommendations": [r.to_dict() for r in top],
        "total_matches": len(candidates),
    }


def discover_hidden_gems(system: str = "", min_rating: float = 70,
                         max_popularity: int = 5, limit: int = 15) -> Dict[str, Any]:
    """Discover hidden gems — high-rated but less popular games.

    Args:
        system: Filter to a specific system
        min_rating: Minimum rating threshold
        max_popularity: Max times a game appears in recommendations
        limit: Max results

    Returns:
        Hidden gem games that are highly rated but less well-known
    """
    profiles = _load_collection()
    if not profiles:
        return {"error": "No metadata in database"}

    if system:
        profiles = [p for p in profiles if p.system == system]

    # Count name frequency as a proxy for popularity
    name_freq = Counter(p.name.lower() for p in profiles)

    gems = []
    for p in profiles:
        try:
            rating = float(p.rating)
        except (ValueError, TypeError):
            continue

        if rating < min_rating:
            continue

        popularity = name_freq.get(p.name.lower(), 0)
        if popularity > max_popularity:
            continue

        # Hidden gem score: high rating + low popularity
        gem_score = rating + (100 - popularity * 20)

        gems.append({
            "game_name": p.name,
            "system": p.system,
            "genre": p.genre,
            "year": p.year,
            "developer": p.developer,
            "rating": p.rating,
            "gem_score": round(gem_score, 1),
            "reason": f"Rating {rating:.0f} but rarely mentioned",
        })

    gems.sort(key=lambda g: g["gem_score"], reverse=True)

    return {
        "hidden_gems": gems[:limit],
        "total_found": len(gems),
        "criteria": {"min_rating": min_rating, "system": system},
    }


def genre_cluster_report(system: str = "") -> Dict[str, Any]:
    """Generate a genre/era/style cluster report for the collection.

    Returns games grouped by genre clusters with stats.
    """
    profiles = _load_collection()
    if system:
        profiles = [p for p in profiles if p.system == system]

    clusters: Dict[str, List[str]] = defaultdict(list)
    era_clusters: Dict[str, List[str]] = defaultdict(list)

    for p in profiles:
        for g in p.normalized_genres:
            clusters[g].append(f"{p.name} ({p.system})")
        era_clusters[p.era].append(f"{p.name} ({p.system})")

    genre_report = {}
    for genre, games in sorted(clusters.items(), key=lambda x: -len(x[1])):
        genre_report[genre] = {
            "count": len(games),
            "sample": games[:5],
        }

    era_report = {}
    for era, games in sorted(era_clusters.items(), key=lambda x: -len(x[1])):
        era_report[era] = {
            "count": len(games),
            "sample": games[:5],
        }

    return {
        "total_games": len(profiles),
        "genre_clusters": genre_report,
        "era_clusters": era_report,
        "dominant_genre": max(clusters, key=lambda g: len(clusters[g])) if clusters else "none",
        "dominant_era": max(era_clusters, key=lambda e: len(era_clusters[e])) if era_clusters else "none",
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python game_recommender.py analyze [system]")
        print("  python game_recommender.py similar <game> [system]")
        print("  python game_recommender.py gems [system]")
        print("  python game_recommender.py clusters [system]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "analyze":
        sys_filter = sys.argv[2] if len(sys.argv) > 2 else ""
        result = analyze_collection(sys_filter)
        print(json.dumps(result, indent=2))

    elif cmd == "similar":
        game = sys.argv[2] if len(sys.argv) > 2 else ""
        sys_filter = sys.argv[3] if len(sys.argv) > 3 else ""
        if not game:
            print("Need game name")
        else:
            result = recommend_similar(game, sys_filter)
            print(json.dumps(result, indent=2))

    elif cmd == "gems":
        sys_filter = sys.argv[2] if len(sys.argv) > 2 else ""
        result = discover_hidden_gems(sys_filter)
        print(json.dumps(result, indent=2))

    elif cmd == "clusters":
        sys_filter = sys.argv[2] if len(sys.argv) > 2 else ""
        result = genre_cluster_report(sys_filter)
        print(json.dumps(result, indent=2))
