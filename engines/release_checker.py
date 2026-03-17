"""GitHub Release Checker — polls emulator repos for new versions.

Compares installed emulator versions against latest GitHub releases.
Feeds into the safe update pipeline (update_manager.py).
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger, audit
from core import database as db
from core.config import get

log = get_logger("release_checker")

# ── Known emulator GitHub repos ─────────────────────────────────────
EMULATOR_REPOS = {
    "MAME": {
        "owner": "mamedev", "repo": "mame",
        "asset_pattern": r"mame\d+b_64bit\.exe|mame\d+lx\.zip",
        "local_dir": "MAME",
        "version_file": "this is MAME *.txt",
        "version_regex": r"MAME\s+([\d.]+)",
    },
    "RetroArch": {
        "owner": "libretro", "repo": "RetroArch",
        "asset_pattern": r"RetroArch.*\.7z|RetroArch.*win.*\.zip",
        "local_dir": "RetroArch",
    },
    "Dolphin": {
        "owner": "dolphin-emu", "repo": "dolphin",
        "asset_pattern": r"dolphin.*x64.*\.7z",
        "local_dir": "Dolphin",
    },
    "PCSX2": {
        "owner": "PCSX2", "repo": "pcsx2",
        "asset_pattern": r"pcsx2.*windows.*x64.*\.7z",
        "local_dir": "PCSX2",
    },
    "RPCS3": {
        "owner": "RPCS3", "repo": "rpcs3-binaries-win",
        "asset_pattern": r"rpcs3.*win64.*\.7z",
        "local_dir": "Rpcs3",
    },
    "PPSSPP": {
        "owner": "hrydgard", "repo": "ppsspp",
        "asset_pattern": r"PPSSPPWindows64.*\.zip",
        "local_dir": "PPSSPP",
    },
    "Cemu": {
        "owner": "cemu-project", "repo": "Cemu",
        "asset_pattern": r"cemu.*windows.*x64.*\.zip",
        "local_dir": "Cemu",
    },
    "DeSmuME": {
        "owner": "TASEmulators", "repo": "desmume",
        "asset_pattern": r"desmume.*win.*x64.*\.zip",
        "local_dir": "DeSmuME",
    },
    "Snes9x": {
        "owner": "snes9xgit", "repo": "snes9x",
        "asset_pattern": r"snes9x.*win32.*x64.*\.zip",
        "local_dir": "Snes9x",
    },
    "VisualBoyAdvance-M": {
        "owner": "visualboyadvance-m", "repo": "visualboyadvance-m",
        "asset_pattern": r"visualboyadvance-m.*Win-x86_64.*\.zip",
        "local_dir": "VisualBoyAdvance-M",
    },
    "Stella": {
        "owner": "stella-emu", "repo": "stella",
        "asset_pattern": r"Stella.*x64.*\.exe|Stella.*windows.*\.zip",
        "local_dir": "Stella",
    },
    "FCEUX": {
        "owner": "TASEmulators", "repo": "fceux",
        "asset_pattern": r"fceux.*win64.*\.zip",
        "local_dir": "Fceux",
    },
    "Nestopia": {
        "owner": "0ldsk00l", "repo": "nestopia",
        "asset_pattern": r"nestopia.*win64.*\.zip",
        "local_dir": "Nestopia",
    },
    "ScummVM": {
        "owner": "scummvm", "repo": "scummvm",
        "asset_pattern": r"scummvm.*win32-x86_64.*\.zip",
        "local_dir": "ScummVM",
    },
    "Hatari": {
        "owner": "hatari", "repo": "hatari",
        "asset_pattern": r"hatari.*win.*\.zip",
        "local_dir": "Hatari",
    },
    "Mupen64Plus": {
        "owner": "mupen64plus", "repo": "mupen64plus-core",
        "asset_pattern": r"mupen64plus.*win.*\.zip",
        "local_dir": "Mupen64Plus",
    },
    "TeknoParrot": {
        "owner": "teknogods", "repo": "TeknoParrotUI",
        "asset_pattern": r"TeknoParrot.*\.zip",
        "local_dir": "TeknoParrot",
    },
    "Mednafen": {
        "owner": "mednafen", "repo": "mednafen",
        "local_dir": "Mednafen",
        "fallback_url": "https://mednafen.github.io/releases/",
    },
    "DOSBox-X": {
        "owner": "joncampbell123", "repo": "dosbox-x",
        "asset_pattern": r"dosbox-x.*win.*x64.*\.zip",
        "local_dir": "DOSBox",
    },
}

GITHUB_API = "https://api.github.com"
RATE_LIMIT_PAUSE = 2  # seconds between API calls to avoid rate limiting


def _get_headers() -> dict:
    """Build GitHub API headers. Uses token from config if available."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "HyperSpin-Toolkit/2.0"}
    token = get("github.token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_latest_release(owner: str, repo: str) -> Optional[dict]:
    """Fetch the latest release from a GitHub repository."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/releases/latest"
    try:
        resp = httpx.get(url, headers=_get_headers(), timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "tag": data.get("tag_name", ""),
                "name": data.get("name", ""),
                "published": data.get("published_at", ""),
                "url": data.get("html_url", ""),
                "prerelease": data.get("prerelease", False),
                "assets": [
                    {
                        "name": a["name"],
                        "size": a["size"],
                        "download_url": a["browser_download_url"],
                    }
                    for a in data.get("assets", [])
                ],
            }
        elif resp.status_code == 404:
            log.warning("No releases found for %s/%s", owner, repo)
        elif resp.status_code == 403:
            log.warning("Rate limited on %s/%s — pause and retry", owner, repo)
        else:
            log.warning("GitHub API %d for %s/%s", resp.status_code, owner, repo)
    except Exception as exc:
        log.error("Failed to fetch release for %s/%s: %s", owner, repo, exc)
    return None


def detect_local_version(emulator_name: str) -> Optional[str]:
    """Attempt to detect the installed version of an emulator."""
    info = EMULATOR_REPOS.get(emulator_name)
    if not info:
        return None

    emu_root = Path(get("paths.emulators_root", ""))
    local_dir = emu_root / info["local_dir"]

    if not local_dir.exists():
        return None

    # Method 1: Look for version text files (like MAME's "this is MAME 0.228.txt")
    version_pattern = info.get("version_file")
    if version_pattern:
        import glob
        matches = glob.glob(str(local_dir / version_pattern))
        if matches:
            fname = Path(matches[0]).name
            ver_re = info.get("version_regex", r"([\d.]+)")
            m = re.search(ver_re, fname)
            if m:
                return m.group(1)

    # Method 2: Check exe file metadata via modification date
    for ext in ("*.exe",):
        import glob
        exes = glob.glob(str(local_dir / ext))
        if exes:
            newest = max(exes, key=lambda f: Path(f).stat().st_mtime)
            mtime = datetime.fromtimestamp(Path(newest).stat().st_mtime)
            return f"unknown (modified {mtime.strftime('%Y-%m-%d')})"

    return "unknown"


def find_matching_asset(release: dict, pattern: str) -> Optional[dict]:
    """Find a Windows x64 asset matching the given regex pattern."""
    if not pattern:
        return None
    for asset in release.get("assets", []):
        if re.search(pattern, asset["name"], re.IGNORECASE):
            return asset
    return None


def check_all_emulators() -> list[dict]:
    """Check all tracked emulators for available updates.

    Returns a list of dicts with update information.
    """
    results = []
    emu_root = Path(get("paths.emulators_root", ""))

    for name, info in EMULATOR_REPOS.items():
        local_dir = emu_root / info["local_dir"]
        installed = local_dir.exists()
        local_version = detect_local_version(name) if installed else None

        log.info("Checking %s ...", name)

        release = fetch_latest_release(info["owner"], info["repo"])
        time.sleep(RATE_LIMIT_PAUSE)

        result = {
            "emulator": name,
            "installed": installed,
            "local_dir": str(local_dir),
            "local_version": local_version,
            "latest_tag": None,
            "latest_name": None,
            "published": None,
            "update_available": False,
            "download_url": None,
            "download_size": None,
            "release_url": None,
        }

        if release:
            result["latest_tag"] = release["tag"]
            result["latest_name"] = release["name"]
            result["published"] = release["published"]
            result["release_url"] = release["url"]

            # Find matching download asset
            asset_pattern = info.get("asset_pattern")
            if asset_pattern:
                asset = find_matching_asset(release, asset_pattern)
                if asset:
                    result["download_url"] = asset["download_url"]
                    result["download_size"] = asset["size"]

            # Determine if update is available
            if local_version and release["tag"]:
                tag_version = re.sub(r"^v", "", release["tag"])
                if local_version != tag_version and "unknown" not in str(local_version):
                    result["update_available"] = True
                elif "unknown" in str(local_version):
                    result["update_available"] = True  # Can't confirm, flag for review

        results.append(result)

        # Store in database
        try:
            db.insert("audit_events", {
                "action": "release_check",
                "target": name,
                "details": json.dumps({
                    "local": local_version,
                    "latest": result.get("latest_tag"),
                    "update_available": result["update_available"],
                }),
                "severity": "WARNING" if result["update_available"] else "INFO",
            })
        except Exception:
            pass

    audit("release_check_complete", f"Checked {len(results)} emulators")
    return results


def check_single_emulator(name: str) -> Optional[dict]:
    """Check a single emulator for updates."""
    if name not in EMULATOR_REPOS:
        log.error("Unknown emulator: %s. Known: %s", name, list(EMULATOR_REPOS.keys()))
        return None

    info = EMULATOR_REPOS[name]
    release = fetch_latest_release(info["owner"], info["repo"])
    if not release:
        return None

    local_version = detect_local_version(name)
    asset = find_matching_asset(release, info.get("asset_pattern", ""))

    return {
        "emulator": name,
        "local_version": local_version,
        "latest_tag": release["tag"],
        "latest_name": release["name"],
        "published": release["published"],
        "release_url": release["url"],
        "download_url": asset["download_url"] if asset else None,
        "download_size": asset["size"] if asset else None,
        "update_available": True,  # If we fetched a release, assume review needed
    }


def download_update(emulator_name: str, target_dir: Optional[Path] = None) -> Optional[Path]:
    """Download the latest release asset for an emulator.

    Returns the path to the downloaded file, or None on failure.
    """
    result = check_single_emulator(emulator_name)
    if not result or not result.get("download_url"):
        log.error("No download URL found for %s", emulator_name)
        return None

    if target_dir is None:
        target_dir = Path(get("paths.output_root", "")) / "downloads"
    target_dir.mkdir(parents=True, exist_ok=True)

    url = result["download_url"]
    filename = url.split("/")[-1]
    filepath = target_dir / filename

    log.info("Downloading %s (%s) ...", filename, _human_size(result.get("download_size", 0)))

    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

        log.info("Downloaded: %s (%s)", filepath, _human_size(filepath.stat().st_size))
        audit("emulator_downloaded", f"{emulator_name}: {filename}")
        return filepath

    except Exception as exc:
        log.error("Download failed for %s: %s", emulator_name, exc)
        if filepath.exists():
            filepath.unlink()
        return None


def get_update_report() -> dict:
    """Generate a summary report of all emulator update statuses."""
    results = check_all_emulators()

    installed = [r for r in results if r["installed"]]
    updates = [r for r in results if r["update_available"]]
    missing = [r for r in results if not r["installed"]]

    return {
        "checked": len(results),
        "installed": len(installed),
        "updates_available": len(updates),
        "not_installed": len(missing),
        "emulators": results,
        "updates": updates,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human readable string."""
    if not size_bytes:
        return "unknown"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
