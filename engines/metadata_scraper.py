"""
M54 -- Metadata Scraping Engine

Structured scraping from game databases:
  - ScreenScraper API (most complete: box art, fanart, marquee, video, wheel)
  - TheGamesDB API (good for modern games, free tier)
  - IGDB API (comprehensive, requires Twitch OAuth)
  - ArcadeDB API (specialized for arcade platforms)
  - SQLite game_metadata table for persistent storage
  - Rate limiting, retry logic, credential management
  - Media download with progress tracking

Note: API keys are loaded from environment variables or toolkit config.
      Users must supply their own credentials.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("metadata_scraper")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = TOOLKIT_ROOT / "data" / "game_metadata.db"
CREDS_PATH = TOOLKIT_ROOT / "config" / "scraper_credentials.json"

# -----------------------------------------------------------------------
# Rate limiter
# -----------------------------------------------------------------------

class RateLimiter:
    """Simple per-source rate limiter with configurable requests/sec."""

    def __init__(self):
        self._last_call: Dict[str, float] = {}
        self._intervals: Dict[str, float] = {
            "screenscraper": 1.2,   # ~50 req/min
            "thegamesdb": 0.5,      # generous free tier
            "igdb": 0.25,           # 4 req/sec with Twitch auth
            "arcadedb": 1.0,        # conservative
        }

    def wait(self, source: str) -> None:
        interval = self._intervals.get(source, 1.0)
        last = self._last_call.get(source, 0)
        elapsed = time.time() - last
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_call[source] = time.time()


_limiter = RateLimiter()


# -----------------------------------------------------------------------
# Credential management
# -----------------------------------------------------------------------

def _load_credentials() -> Dict[str, Any]:
    """Load API credentials from config file or environment variables."""
    creds: Dict[str, Any] = {}

    # Try config file first
    if CREDS_PATH.exists():
        try:
            creds = json.loads(CREDS_PATH.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to load credentials file: %s", e)

    # Environment variable overrides
    env_map = {
        "screenscraper": {
            "devid": "SCREENSCRAPER_DEVID",
            "devpassword": "SCREENSCRAPER_DEVPASSWORD",
            "softname": "SCREENSCRAPER_SOFTNAME",
            "ssid": "SCREENSCRAPER_SSID",
            "sspassword": "SCREENSCRAPER_SSPASSWORD",
        },
        "thegamesdb": {
            "apikey": "THEGAMESDB_APIKEY",
        },
        "igdb": {
            "client_id": "IGDB_CLIENT_ID",
            "client_secret": "IGDB_CLIENT_SECRET",
        },
    }

    for source, keys in env_map.items():
        if source not in creds:
            creds[source] = {}
        for key, env_var in keys.items():
            val = os.environ.get(env_var, "")
            if val:
                creds[source][key] = val

    return creds


def save_credentials(creds: Dict[str, Any]) -> str:
    """Save credentials to config file."""
    os.makedirs(CREDS_PATH.parent, exist_ok=True)
    CREDS_PATH.write_text(json.dumps(creds, indent=2), encoding="utf-8")
    return str(CREDS_PATH)


# -----------------------------------------------------------------------
# Data model
# -----------------------------------------------------------------------

@dataclass
class GameMetadata:
    """Standardized game metadata from any source."""
    game_name: str
    system: str
    source: str = ""           # screenscraper, thegamesdb, igdb, arcadedb
    source_id: str = ""        # ID in the source database
    title: str = ""
    description: str = ""
    year: str = ""
    developer: str = ""
    publisher: str = ""
    genre: str = ""
    players: str = ""
    rating: str = ""
    region: str = ""
    # Media URLs
    box_art_url: str = ""
    wheel_art_url: str = ""
    fanart_url: str = ""
    marquee_url: str = ""
    screenshot_url: str = ""
    video_url: str = ""
    manual_url: str = ""
    # Local paths (after download)
    box_art_path: str = ""
    wheel_art_path: str = ""
    fanart_path: str = ""
    marquee_path: str = ""
    screenshot_path: str = ""
    video_path: str = ""
    manual_path: str = ""
    # Metadata
    scraped_at: str = ""
    raw_json: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if "raw_json" in d:
            del d["raw_json"]  # Don't include bulky raw data in API responses
        return d


# -----------------------------------------------------------------------
# SQLite storage
# -----------------------------------------------------------------------

def _ensure_db() -> sqlite3.Connection:
    """Create/open the game metadata SQLite database."""
    os.makedirs(DB_PATH.parent, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS game_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_name TEXT NOT NULL,
            system TEXT NOT NULL,
            source TEXT NOT NULL,
            source_id TEXT,
            title TEXT,
            description TEXT,
            year TEXT,
            developer TEXT,
            publisher TEXT,
            genre TEXT,
            players TEXT,
            rating TEXT,
            region TEXT,
            box_art_url TEXT,
            wheel_art_url TEXT,
            fanart_url TEXT,
            marquee_url TEXT,
            screenshot_url TEXT,
            video_url TEXT,
            manual_url TEXT,
            box_art_path TEXT,
            wheel_art_path TEXT,
            fanart_path TEXT,
            marquee_path TEXT,
            screenshot_path TEXT,
            video_path TEXT,
            manual_path TEXT,
            scraped_at TEXT,
            raw_json TEXT,
            UNIQUE(game_name, system, source)
        );

        CREATE INDEX IF NOT EXISTS idx_meta_system ON game_metadata(system);
        CREATE INDEX IF NOT EXISTS idx_meta_source ON game_metadata(source);
        CREATE INDEX IF NOT EXISTS idx_meta_name ON game_metadata(game_name);

        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system TEXT NOT NULL,
            source TEXT NOT NULL,
            total_games INTEGER DEFAULT 0,
            scraped INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            started_at TEXT,
            finished_at TEXT,
            status TEXT DEFAULT 'pending'
        );
    """)
    conn.commit()
    return conn


def store_metadata(meta: GameMetadata) -> None:
    """Store or update game metadata in SQLite."""
    conn = _ensure_db()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO game_metadata
            (game_name, system, source, source_id, title, description,
             year, developer, publisher, genre, players, rating, region,
             box_art_url, wheel_art_url, fanart_url, marquee_url,
             screenshot_url, video_url, manual_url,
             box_art_path, wheel_art_path, fanart_path, marquee_path,
             screenshot_path, video_path, manual_path,
             scraped_at, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            meta.game_name, meta.system, meta.source, meta.source_id,
            meta.title, meta.description, meta.year, meta.developer,
            meta.publisher, meta.genre, meta.players, meta.rating, meta.region,
            meta.box_art_url, meta.wheel_art_url, meta.fanart_url,
            meta.marquee_url, meta.screenshot_url, meta.video_url,
            meta.manual_url, meta.box_art_path, meta.wheel_art_path,
            meta.fanart_path, meta.marquee_path, meta.screenshot_path,
            meta.video_path, meta.manual_path, meta.scraped_at, meta.raw_json,
        ))
        conn.commit()
    finally:
        conn.close()


def get_metadata(game_name: str, system: str,
                 source: Optional[str] = None) -> Optional[GameMetadata]:
    """Retrieve stored metadata for a game."""
    conn = _ensure_db()
    try:
        if source:
            row = conn.execute(
                "SELECT * FROM game_metadata WHERE game_name=? AND system=? AND source=?",
                (game_name, system, source)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM game_metadata WHERE game_name=? AND system=? ORDER BY scraped_at DESC",
                (game_name, system)
            ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in conn.execute("SELECT * FROM game_metadata LIMIT 0").description]
        d = dict(zip(cols, row))
        return GameMetadata(**{k: v for k, v in d.items() if k != "id"})
    finally:
        conn.close()


def search_metadata(query: str, system: Optional[str] = None,
                    limit: int = 50) -> List[Dict]:
    """Search stored metadata by game name."""
    conn = _ensure_db()
    try:
        sql = "SELECT game_name, system, source, title, year, genre, rating FROM game_metadata WHERE game_name LIKE ?"
        params: list = [f"%{query}%"]
        if system:
            sql += " AND system = ?"
            params.append(system)
        sql += " ORDER BY game_name LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [
            {"game_name": r[0], "system": r[1], "source": r[2],
             "title": r[3], "year": r[4], "genre": r[5], "rating": r[6]}
            for r in rows
        ]
    finally:
        conn.close()


def get_scrape_stats() -> Dict[str, Any]:
    """Get overall scraping statistics."""
    conn = _ensure_db()
    try:
        total = conn.execute("SELECT COUNT(*) FROM game_metadata").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) FROM game_metadata GROUP BY source"
        ).fetchall()
        by_system = conn.execute(
            "SELECT system, COUNT(*) FROM game_metadata GROUP BY system ORDER BY COUNT(*) DESC LIMIT 20"
        ).fetchall()
        return {
            "total_entries": total,
            "by_source": {r[0]: r[1] for r in by_source},
            "top_systems": {r[0]: r[1] for r in by_system},
        }
    finally:
        conn.close()


# -----------------------------------------------------------------------
# HTTP helpers with retry
# -----------------------------------------------------------------------

def _http_get(url: str, headers: Optional[Dict[str, str]] = None,
              retries: int = 3, timeout: int = 30) -> Optional[bytes]:
    """HTTP GET with retry logic."""
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:  # Rate limited
                wait = min(2 ** attempt * 2, 30)
                logger.warning("Rate limited on %s, waiting %ds", url[:80], wait)
                time.sleep(wait)
            elif e.code in (500, 502, 503):
                time.sleep(2 ** attempt)
            else:
                logger.error("HTTP %d for %s", e.code, url[:100])
                return None
        except Exception as e:
            logger.warning("Request failed (attempt %d): %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None


def _http_post(url: str, body: str, headers: Optional[Dict[str, str]] = None,
               retries: int = 3, timeout: int = 30) -> Optional[bytes]:
    """HTTP POST with retry logic."""
    data = body.encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(min(2 ** attempt * 2, 30))
            elif e.code in (500, 502, 503):
                time.sleep(2 ** attempt)
            else:
                logger.error("HTTP POST %d for %s", e.code, url[:100])
                return None
        except Exception as e:
            logger.warning("POST failed (attempt %d): %s", attempt + 1, e)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

    return None


# -----------------------------------------------------------------------
# ScreenScraper API
# -----------------------------------------------------------------------

SCREENSCRAPER_BASE = "https://api.screenscraper.fr/api2"

# System ID mapping for ScreenScraper
SS_SYSTEM_IDS: Dict[str, int] = {
    "MAME": 75, "Arcade": 75,
    "Nintendo Entertainment System": 3, "NES": 3,
    "Super Nintendo": 4, "SNES": 4,
    "Nintendo 64": 14, "N64": 14,
    "Game Boy": 9, "GB": 9,
    "Game Boy Color": 10, "GBC": 10,
    "Game Boy Advance": 12, "GBA": 12,
    "Nintendo DS": 15, "NDS": 15,
    "Nintendo GameCube": 13, "GameCube": 13,
    "Nintendo Wii": 16, "Wii": 16,
    "Sega Master System": 2, "SMS": 2,
    "Sega Genesis": 1, "Mega Drive": 1, "Genesis": 1,
    "Sega Saturn": 22, "Saturn": 22,
    "Sega Dreamcast": 23, "Dreamcast": 23,
    "Sega CD": 20, "Mega CD": 20,
    "Sega Game Gear": 21, "Game Gear": 21,
    "PlayStation": 57, "PS1": 57, "PSX": 57,
    "PlayStation 2": 58, "PS2": 58,
    "PlayStation Portable": 61, "PSP": 61,
    "TurboGrafx-16": 31, "PC Engine": 31,
    "Neo Geo": 142, "Neo Geo AES": 142,
    "Neo Geo CD": 70,
    "Atari 2600": 26, "Atari 5200": 40, "Atari 7800": 41,
    "Atari Lynx": 28, "Atari Jaguar": 27,
    "ColecoVision": 48, "Intellivision": 115,
    "MSX": 113, "MSX2": 116,
    "Amstrad CPC": 65, "ZX Spectrum": 76,
    "Commodore 64": 66, "C64": 66,
    "Amiga": 64, "Commodore Amiga": 64,
    "3DO": 29, "Philips CD-i": 133,
    "WonderSwan": 45, "WonderSwan Color": 46,
    "Vectrex": 102, "Virtual Boy": 11,
    "PC-FX": 72, "PC-98": 208,
    "Nintendo Switch": 225, "Switch": 225,
    "PlayStation Vita": 62, "Vita": 62,
}


def scrape_screenscraper(game_name: str, system: str,
                         rom_path: str = "", creds: Optional[Dict] = None) -> Optional[GameMetadata]:
    """Scrape game metadata from ScreenScraper API."""
    all_creds = creds or _load_credentials()
    ss_creds = all_creds.get("screenscraper", {})

    if not ss_creds.get("devid") or not ss_creds.get("devpassword"):
        logger.warning("ScreenScraper credentials not configured")
        return None

    system_id = SS_SYSTEM_IDS.get(system)
    if system_id is None:
        logger.warning("Unknown system for ScreenScraper: %s", system)
        return None

    _limiter.wait("screenscraper")

    params = {
        "devid": ss_creds["devid"],
        "devpassword": ss_creds["devpassword"],
        "softname": ss_creds.get("softname", "KINHANKToolkit"),
        "output": "json",
        "systemeid": str(system_id),
        "romnom": f"{game_name}.zip",
    }
    if ss_creds.get("ssid"):
        params["ssid"] = ss_creds["ssid"]
        params["sspassword"] = ss_creds.get("sspassword", "")

    url = f"{SCREENSCRAPER_BASE}/jeuInfos.php?{urllib.parse.urlencode(params)}"
    data = _http_get(url)
    if not data:
        return None

    try:
        resp = json.loads(data)
        jeu = resp.get("response", {}).get("jeu", {})
        if not jeu:
            return None
    except (json.JSONDecodeError, KeyError):
        return None

    # Extract text fields (prefer English, fallback to first available)
    def _get_text(obj: Any, lang: str = "en") -> str:
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and item.get("langue") == lang:
                    return item.get("text", "")
            return obj[0].get("text", "") if obj else ""
        if isinstance(obj, dict):
            return obj.get("text", str(obj))
        return str(obj) if obj else ""

    meta = GameMetadata(
        game_name=game_name,
        system=system,
        source="screenscraper",
        source_id=str(jeu.get("id", "")),
        title=_get_text(jeu.get("noms", [{}])),
        description=_get_text(jeu.get("synopsis", [])),
        year=jeu.get("dates", {}).get("date_wor", jeu.get("dates", {}).get("date_usa", "")),
        developer=_get_text(jeu.get("developpeur", "")),
        publisher=_get_text(jeu.get("editeur", "")),
        genre=_get_text(jeu.get("genres", [{}])),
        players=str(jeu.get("joueurs", {}).get("text", "")),
        rating=str(jeu.get("note", {}).get("text", "")),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        raw_json=json.dumps(jeu, ensure_ascii=False)[:10000],
    )

    # Extract media URLs
    medias = jeu.get("medias", [])
    for m in medias:
        mtype = m.get("type", "")
        url_val = m.get("url", "")
        region = m.get("region", "")
        if mtype == "box-2D" and (region in ("us", "wor", "") or not meta.box_art_url):
            meta.box_art_url = url_val
        elif mtype == "wheel" and not meta.wheel_art_url:
            meta.wheel_art_url = url_val
        elif mtype == "fanart" and not meta.fanart_url:
            meta.fanart_url = url_val
        elif mtype == "marquee" and not meta.marquee_url:
            meta.marquee_url = url_val
        elif mtype == "ss" and not meta.screenshot_url:
            meta.screenshot_url = url_val
        elif mtype == "video" and not meta.video_url:
            meta.video_url = url_val
        elif mtype == "manuel" and not meta.manual_url:
            meta.manual_url = url_val

    return meta


# -----------------------------------------------------------------------
# TheGamesDB API
# -----------------------------------------------------------------------

TGDB_BASE = "https://api.thegamesdb.net/v1.1"

TGDB_PLATFORM_IDS: Dict[str, int] = {
    "NES": 7, "SNES": 6, "N64": 3, "GameCube": 2, "Wii": 9,
    "Game Boy": 4, "GBA": 5, "NDS": 8,
    "Genesis": 18, "Sega CD": 21, "Saturn": 17, "Dreamcast": 16,
    "Game Gear": 20, "Master System": 35,
    "PlayStation": 10, "PS2": 11, "PSP": 13,
    "TurboGrafx-16": 34, "Neo Geo": 24,
    "Atari 2600": 22, "Atari 7800": 43, "Jaguar": 28,
    "3DO": 25, "Arcade": 23, "MAME": 23,
}


def scrape_thegamesdb(game_name: str, system: str,
                      creds: Optional[Dict] = None) -> Optional[GameMetadata]:
    """Scrape game metadata from TheGamesDB API."""
    all_creds = creds or _load_credentials()
    apikey = all_creds.get("thegamesdb", {}).get("apikey", "")
    if not apikey:
        logger.warning("TheGamesDB API key not configured")
        return None

    platform_id = TGDB_PLATFORM_IDS.get(system)

    _limiter.wait("thegamesdb")

    params = {
        "apikey": apikey,
        "name": game_name,
        "fields": "players,publishers,genres,overview,last_updated,rating,platform,coop,youtube,os,processor,ram,hdd,video,sound,alternates",
    }
    if platform_id:
        params["filter[platform]"] = str(platform_id)

    url = f"{TGDB_BASE}/Games/ByGameName?{urllib.parse.urlencode(params)}"
    data = _http_get(url)
    if not data:
        return None

    try:
        resp = json.loads(data)
        games = resp.get("data", {}).get("games", [])
        if not games:
            return None
        game = games[0]  # Best match
    except (json.JSONDecodeError, KeyError, IndexError):
        return None

    meta = GameMetadata(
        game_name=game_name,
        system=system,
        source="thegamesdb",
        source_id=str(game.get("id", "")),
        title=game.get("game_title", game_name),
        description=game.get("overview", ""),
        year=game.get("release_date", "")[:4] if game.get("release_date") else "",
        developer=str(game.get("developers", [""])[0]) if game.get("developers") else "",
        publisher=str(game.get("publishers", [""])[0]) if game.get("publishers") else "",
        players=str(game.get("players", "")),
        rating=str(game.get("rating", "")),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        raw_json=json.dumps(game, ensure_ascii=False)[:10000],
    )

    # Fetch box art from images endpoint
    game_id = game.get("id")
    if game_id:
        img_url = f"{TGDB_BASE}/Games/Images?apikey={apikey}&games_id={game_id}"
        img_data = _http_get(img_url)
        if img_data:
            try:
                img_resp = json.loads(img_data)
                base_url = img_resp.get("data", {}).get("base_url", {}).get("original", "")
                images = img_resp.get("data", {}).get("images", {}).get(str(game_id), [])
                for img in images:
                    itype = img.get("type", "")
                    iurl = base_url + img.get("filename", "")
                    if itype == "boxart" and img.get("side") == "front" and not meta.box_art_url:
                        meta.box_art_url = iurl
                    elif itype == "fanart" and not meta.fanart_url:
                        meta.fanart_url = iurl
                    elif itype == "screenshot" and not meta.screenshot_url:
                        meta.screenshot_url = iurl
                    elif itype == "clearlogo" and not meta.wheel_art_url:
                        meta.wheel_art_url = iurl
                    elif itype == "banner" and not meta.marquee_url:
                        meta.marquee_url = iurl
            except Exception:
                pass

    return meta


# -----------------------------------------------------------------------
# IGDB API (via Twitch OAuth)
# -----------------------------------------------------------------------

IGDB_BASE = "https://api.igdb.com/v4"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"

_igdb_token_cache: Dict[str, Any] = {}


def _get_igdb_token(creds: Dict) -> Optional[str]:
    """Get or refresh IGDB access token via Twitch OAuth."""
    igdb_creds = creds.get("igdb", {})
    client_id = igdb_creds.get("client_id", "")
    client_secret = igdb_creds.get("client_secret", "")
    if not client_id or not client_secret:
        return None

    # Check cache
    if _igdb_token_cache.get("token") and _igdb_token_cache.get("expires", 0) > time.time():
        return _igdb_token_cache["token"]

    params = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    })
    data = _http_post(f"{TWITCH_TOKEN_URL}?{params}", "",
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    if not data:
        return None

    try:
        resp = json.loads(data)
        token = resp.get("access_token")
        expires_in = resp.get("expires_in", 3600)
        _igdb_token_cache["token"] = token
        _igdb_token_cache["expires"] = time.time() + expires_in - 60
        return token
    except Exception:
        return None


def scrape_igdb(game_name: str, system: str,
                creds: Optional[Dict] = None) -> Optional[GameMetadata]:
    """Scrape game metadata from IGDB API."""
    all_creds = creds or _load_credentials()
    token = _get_igdb_token(all_creds)
    if not token:
        logger.warning("IGDB credentials not configured or token fetch failed")
        return None

    client_id = all_creds.get("igdb", {}).get("client_id", "")
    _limiter.wait("igdb")

    # Search for the game
    body = f'search "{game_name}"; fields name,summary,first_release_date,genres.name,involved_companies.company.name,involved_companies.developer,involved_companies.publisher,rating,cover.url,screenshots.url,artworks.url,videos.video_id; limit 1;'
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
        "Content-Type": "text/plain",
    }
    data = _http_post(f"{IGDB_BASE}/games", body, headers=headers)
    if not data:
        return None

    try:
        results = json.loads(data)
        if not results:
            return None
        game = results[0]
    except (json.JSONDecodeError, IndexError):
        return None

    # Extract developers and publishers
    developer = ""
    publisher = ""
    for ic in game.get("involved_companies", []):
        company = ic.get("company", {})
        name = company.get("name", "")
        if ic.get("developer") and not developer:
            developer = name
        if ic.get("publisher") and not publisher:
            publisher = name

    # Release date
    year = ""
    frd = game.get("first_release_date")
    if frd:
        year = datetime.fromtimestamp(frd, tz=timezone.utc).strftime("%Y")

    # Genres
    genres = [g.get("name", "") for g in game.get("genres", [])]

    meta = GameMetadata(
        game_name=game_name,
        system=system,
        source="igdb",
        source_id=str(game.get("id", "")),
        title=game.get("name", game_name),
        description=game.get("summary", ""),
        year=year,
        developer=developer,
        publisher=publisher,
        genre=", ".join(genres),
        rating=str(round(game.get("rating", 0), 1)) if game.get("rating") else "",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        raw_json=json.dumps(game, ensure_ascii=False, default=str)[:10000],
    )

    # Cover
    cover = game.get("cover", {})
    if isinstance(cover, dict) and cover.get("url"):
        meta.box_art_url = "https:" + cover["url"].replace("t_thumb", "t_cover_big")

    # Screenshots
    screenshots = game.get("screenshots", [])
    if screenshots and isinstance(screenshots[0], dict):
        meta.screenshot_url = "https:" + screenshots[0]["url"].replace("t_thumb", "t_screenshot_big")

    # Artworks (fanart)
    artworks = game.get("artworks", [])
    if artworks and isinstance(artworks[0], dict):
        meta.fanart_url = "https:" + artworks[0]["url"].replace("t_thumb", "t_1080p")

    # Video
    videos = game.get("videos", [])
    if videos and isinstance(videos[0], dict):
        vid_id = videos[0].get("video_id", "")
        if vid_id:
            meta.video_url = f"https://www.youtube.com/watch?v={vid_id}"

    return meta


# -----------------------------------------------------------------------
# ArcadeDB API
# -----------------------------------------------------------------------

ARCADEDB_BASE = "http://adb.arcadeitalia.net/service_scraper.php"


def scrape_arcadedb(game_name: str, system: str = "Arcade",
                    creds: Optional[Dict] = None) -> Optional[GameMetadata]:
    """Scrape game metadata from ArcadeDB (Arcade Italia)."""
    _limiter.wait("arcadedb")

    params = {
        "ajax": "query_mame",
        "game_name": game_name,
    }
    url = f"{ARCADEDB_BASE}?{urllib.parse.urlencode(params)}"
    data = _http_get(url)
    if not data:
        return None

    try:
        resp = json.loads(data)
        results = resp.get("result", [])
        if not results:
            return None
        game = results[0]
    except (json.JSONDecodeError, IndexError, KeyError):
        return None

    meta = GameMetadata(
        game_name=game_name,
        system=system,
        source="arcadedb",
        source_id=game.get("game_name", ""),
        title=game.get("title", game_name),
        description=game.get("history", ""),
        year=game.get("year", ""),
        developer=game.get("manufacturer", ""),
        publisher=game.get("manufacturer", ""),
        genre=game.get("genre", ""),
        players=str(game.get("players", "")),
        rating=str(game.get("rate", "")),
        scraped_at=datetime.now(timezone.utc).isoformat(),
        raw_json=json.dumps(game, ensure_ascii=False)[:10000],
    )

    # Media URLs from ArcadeDB
    if game.get("url_image_ingame"):
        meta.screenshot_url = game["url_image_ingame"]
    if game.get("url_image_title"):
        meta.marquee_url = game["url_image_title"]
    if game.get("url_image_flyer"):
        meta.box_art_url = game["url_image_flyer"]
    if game.get("url_image_marquee"):
        meta.marquee_url = game["url_image_marquee"]

    return meta


# -----------------------------------------------------------------------
# Unified scraper
# -----------------------------------------------------------------------

SOURCE_SCRAPERS = {
    "screenscraper": scrape_screenscraper,
    "thegamesdb": scrape_thegamesdb,
    "igdb": scrape_igdb,
    "arcadedb": scrape_arcadedb,
}


def scrape_game(game_name: str, system: str,
                sources: Optional[List[str]] = None,
                store: bool = True) -> Dict[str, Any]:
    """
    Scrape metadata for a game from one or more sources.

    Args:
        game_name: ROM/game name to search for
        system: System name (e.g. "SNES", "PlayStation")
        sources: Which APIs to query (default: all configured)
        store: Store results in SQLite

    Returns:
        Dict with results from each source
    """
    if sources is None:
        sources = list(SOURCE_SCRAPERS.keys())

    results: Dict[str, Any] = {
        "game_name": game_name,
        "system": system,
        "sources_tried": sources,
        "results": {},
    }

    for source in sources:
        scraper = SOURCE_SCRAPERS.get(source)
        if not scraper:
            results["results"][source] = {"error": f"Unknown source: {source}"}
            continue

        try:
            meta = scraper(game_name, system)
            if meta:
                if store:
                    store_metadata(meta)
                results["results"][source] = meta.to_dict()
                logger.info("Scraped %s from %s for %s", game_name, source, system)
            else:
                results["results"][source] = {"found": False}
        except Exception as e:
            logger.error("Scrape error (%s/%s): %s", source, game_name, e)
            results["results"][source] = {"error": str(e)}

    return results


def batch_scrape(game_names: List[str], system: str,
                 sources: Optional[List[str]] = None,
                 store: bool = True,
                 progress_callback=None) -> Dict[str, Any]:
    """
    Batch scrape metadata for multiple games.

    Args:
        game_names: List of game names to scrape
        system: System name
        sources: Which APIs to query
        store: Store results in SQLite
        progress_callback: Called with (index, total, game_name) periodically

    Returns:
        Summary with per-game results
    """
    total = len(game_names)
    successes = 0
    failures = 0
    results_list = []

    for i, name in enumerate(game_names):
        try:
            result = scrape_game(name, system, sources, store)
            has_data = any(
                isinstance(v, dict) and v.get("title")
                for v in result.get("results", {}).values()
            )
            if has_data:
                successes += 1
            else:
                failures += 1
            results_list.append({"game": name, "found": has_data})
        except Exception as e:
            failures += 1
            results_list.append({"game": name, "error": str(e)})

        if progress_callback and (i + 1) % 10 == 0:
            progress_callback(i + 1, total, name)

    return {
        "system": system,
        "total": total,
        "successes": successes,
        "failures": failures,
        "results": results_list[:100],  # Cap output
    }


# -----------------------------------------------------------------------
# Media download
# -----------------------------------------------------------------------

def download_media(meta: GameMetadata, output_dir: str,
                   media_types: Optional[List[str]] = None) -> Dict[str, str]:
    """
    Download media files for a game.

    Args:
        meta: GameMetadata with URLs populated
        output_dir: Base directory for media files
        media_types: Which media to download (default: all available)

    Returns:
        Dict mapping media type to local file path
    """
    out = Path(output_dir)
    os.makedirs(out, exist_ok=True)

    type_map = {
        "box_art": meta.box_art_url,
        "wheel_art": meta.wheel_art_url,
        "fanart": meta.fanart_url,
        "marquee": meta.marquee_url,
        "screenshot": meta.screenshot_url,
        "video": meta.video_url,
        "manual": meta.manual_url,
    }

    if media_types:
        type_map = {k: v for k, v in type_map.items() if k in media_types}

    downloaded: Dict[str, str] = {}
    safe_name = meta.game_name.replace("/", "_").replace("\\", "_").replace(":", "_")

    for mtype, url in type_map.items():
        if not url or url.startswith("https://www.youtube.com"):
            continue

        ext = Path(urllib.parse.urlparse(url).path).suffix or ".png"
        if mtype == "video":
            ext = ext or ".mp4"
        if mtype == "manual":
            ext = ext or ".pdf"

        fname = f"{safe_name}_{mtype}{ext}"
        fpath = out / fname

        if fpath.exists():
            downloaded[mtype] = str(fpath)
            continue

        data = _http_get(url, retries=2, timeout=60)
        if data:
            fpath.write_bytes(data)
            downloaded[mtype] = str(fpath)
            logger.info("Downloaded %s for %s -> %s", mtype, meta.game_name, fpath)

    return downloaded


# -----------------------------------------------------------------------
# Credential status check
# -----------------------------------------------------------------------

def check_credentials() -> Dict[str, Any]:
    """Check which API credentials are configured."""
    creds = _load_credentials()
    status: Dict[str, Any] = {}

    # ScreenScraper
    ss = creds.get("screenscraper", {})
    status["screenscraper"] = {
        "configured": bool(ss.get("devid") and ss.get("devpassword")),
        "has_user": bool(ss.get("ssid")),
        "fields": ["devid", "devpassword", "softname", "ssid", "sspassword"],
    }

    # TheGamesDB
    tgdb = creds.get("thegamesdb", {})
    status["thegamesdb"] = {
        "configured": bool(tgdb.get("apikey")),
        "fields": ["apikey"],
    }

    # IGDB
    igdb = creds.get("igdb", {})
    status["igdb"] = {
        "configured": bool(igdb.get("client_id") and igdb.get("client_secret")),
        "fields": ["client_id", "client_secret"],
    }

    # ArcadeDB (no auth needed)
    status["arcadedb"] = {
        "configured": True,
        "fields": [],
        "note": "No authentication required",
    }

    return status


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python metadata_scraper.py scrape <game> <system> [--source screenscraper]")
        print("  python metadata_scraper.py search <query> [--system SNES]")
        print("  python metadata_scraper.py stats")
        print("  python metadata_scraper.py credentials")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "scrape":
        name = sys.argv[2] if len(sys.argv) > 2 else "Super Mario Bros."
        sys_name = sys.argv[3] if len(sys.argv) > 3 else "NES"
        srcs = None
        if "--source" in sys.argv:
            idx = sys.argv.index("--source")
            srcs = [sys.argv[idx + 1]] if idx + 1 < len(sys.argv) else None
        result = scrape_game(name, sys_name, srcs)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        sys_filter = None
        if "--system" in sys.argv:
            idx = sys.argv.index("--system")
            sys_filter = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        results = search_metadata(q, sys_filter)
        for r in results:
            print(f"  {r['game_name']} ({r['system']}) [{r['source']}] - {r['year']} {r['genre']}")

    elif cmd == "stats":
        stats = get_scrape_stats()
        print(json.dumps(stats, indent=2))

    elif cmd == "credentials":
        status = check_credentials()
        for src, info in status.items():
            icon = "OK" if info["configured"] else "MISSING"
            print(f"  [{icon}] {src}: {info}")
