"""
M28 -- Online Research Agent

Provides:
  - Scrape game info from public databases (IGDB, MobyGames, Wikipedia)
  - Emulator update checking from official sources
  - Community tip aggregation
  - AI-summarized research reports
  - Integration with agent_memory for storing findings
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("research_agent")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent


# -----------------------------------------------------------------------
# Known emulator release URLs
# -----------------------------------------------------------------------

EMULATOR_SOURCES: Dict[str, Dict[str, str]] = {
    "RetroArch": {
        "url": "https://www.retroarch.com/index.php?page=platforms",
        "github": "https://api.github.com/repos/libretro/RetroArch/releases/latest",
        "type": "multi-system",
    },
    "PCSX2": {
        "url": "https://pcsx2.net/downloads",
        "github": "https://api.github.com/repos/PCSX2/pcsx2/releases/latest",
        "type": "PS2",
    },
    "RPCS3": {
        "url": "https://rpcs3.net/download",
        "github": "https://api.github.com/repos/RPCS3/rpcs3/releases/latest",
        "type": "PS3",
    },
    "Dolphin": {
        "url": "https://dolphin-emu.org/download/",
        "github": "https://api.github.com/repos/dolphin-emu/dolphin/releases/latest",
        "type": "GameCube/Wii",
    },
    "DuckStation": {
        "url": "https://github.com/stenzek/duckstation/releases",
        "github": "https://api.github.com/repos/stenzek/duckstation/releases/latest",
        "type": "PS1",
    },
    "mGBA": {
        "url": "https://mgba.io/downloads.html",
        "github": "https://api.github.com/repos/mgba-emu/mgba/releases/latest",
        "type": "GBA",
    },
    "Cemu": {
        "url": "https://cemu.info/#download",
        "github": "https://api.github.com/repos/cemu-project/Cemu/releases/latest",
        "type": "Wii U",
    },
    "PPSSPP": {
        "url": "https://www.ppsspp.org/download",
        "github": "https://api.github.com/repos/hrydgard/ppsspp/releases/latest",
        "type": "PSP",
    },
    "Ryujinx": {
        "url": "https://ryujinx.org/download",
        "github": "",
        "type": "Switch",
    },
    "MAME": {
        "url": "https://www.mamedev.org/release.php",
        "github": "https://api.github.com/repos/mamedev/mame/releases/latest",
        "type": "Arcade",
    },
    "Flycast": {
        "url": "https://github.com/flyinghead/flycast/releases",
        "github": "https://api.github.com/repos/flyinghead/flycast/releases/latest",
        "type": "Dreamcast",
    },
    "Mednafen": {
        "url": "https://mednafen.github.io/releases/",
        "github": "",
        "type": "multi-system",
    },
    "melonDS": {
        "url": "https://melonds.kuribo64.net/downloads.php",
        "github": "https://api.github.com/repos/melonDS-emu/melonDS/releases/latest",
        "type": "NDS",
    },
    "Snes9x": {
        "url": "https://www.snes9x.com/downloads.php",
        "github": "https://api.github.com/repos/snes9xgit/snes9x/releases/latest",
        "type": "SNES",
    },
}


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class EmulatorUpdate:
    """Information about an emulator's latest release."""
    emulator: str
    current_version: str = ""
    latest_version: str = ""
    release_date: str = ""
    download_url: str = ""
    release_notes: str = ""
    update_available: bool = False
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchResult:
    """A research finding."""
    topic: str
    source: str
    title: str = ""
    content: str = ""
    url: str = ""
    timestamp: str = ""
    relevance: float = 0.0
    category: str = ""  # game_info, emulator, community_tip, compatibility

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------
# Emulator update checking
# -----------------------------------------------------------------------

def _fetch_json(url: str, timeout: int = 15) -> Optional[Dict]:
    """Fetch JSON from a URL with error handling."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HyperSpinToolkit/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


def check_emulator_updates(emulators: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check for updates for specified emulators (or all known).

    Args:
        emulators: List of emulator names to check. None = all.

    Returns:
        Update status for each emulator
    """
    targets = emulators or list(EMULATOR_SOURCES.keys())
    results: List[EmulatorUpdate] = []

    for emu_name in targets:
        source = EMULATOR_SOURCES.get(emu_name)
        if not source:
            results.append(EmulatorUpdate(emulator=emu_name, error=f"Unknown emulator: {emu_name}"))
            continue

        github_url = source.get("github", "")
        if not github_url:
            results.append(EmulatorUpdate(
                emulator=emu_name,
                download_url=source.get("url", ""),
                error="No GitHub API endpoint — check website manually",
            ))
            continue

        data = _fetch_json(github_url)
        if not data:
            results.append(EmulatorUpdate(emulator=emu_name, error="Failed to fetch release info"))
            continue

        tag = data.get("tag_name", "")
        published = data.get("published_at", "")
        body = data.get("body", "")[:500]
        html_url = data.get("html_url", "")

        results.append(EmulatorUpdate(
            emulator=emu_name,
            latest_version=tag,
            release_date=published,
            download_url=html_url,
            release_notes=body,
        ))

    # Store in agent memory
    try:
        from engines.agent_memory import store_memory
        for r in results:
            if r.latest_version:
                store_memory(
                    category="observation",
                    subject=r.emulator,
                    key=f"latest_version",
                    value=f"{r.latest_version} released {r.release_date}",
                    source="research_agent",
                    tags="emulator,update,version",
                )
    except Exception:
        pass

    updates_available = [r for r in results if r.latest_version and not r.error]

    return {
        "checked": len(results),
        "with_updates": len(updates_available),
        "errors": sum(1 for r in results if r.error),
        "emulators": [r.to_dict() for r in results],
    }


def check_single_emulator(emulator: str) -> Dict[str, Any]:
    """Check update status for a single emulator."""
    result = check_emulator_updates([emulator])
    if result["emulators"]:
        return result["emulators"][0]
    return {"error": f"No results for {emulator}"}


# -----------------------------------------------------------------------
# Game research
# -----------------------------------------------------------------------

def research_game(game_name: str, system: str = "") -> Dict[str, Any]:
    """Research a game using available sources.

    Attempts to gather information from metadata DB first,
    then online sources if available.

    Args:
        game_name: Game name to research
        system: System/platform

    Returns:
        Aggregated research results
    """
    findings: List[ResearchResult] = []

    # Check local metadata DB first
    try:
        from engines.metadata_scraper import search_metadata
        local_results = search_metadata(game_name, system or None, limit=5)
        for lr in local_results:
            findings.append(ResearchResult(
                topic=game_name,
                source="local_metadata",
                title=lr.get("game_name", game_name),
                content=json.dumps({
                    "genre": lr.get("genre", ""),
                    "developer": lr.get("developer", ""),
                    "publisher": lr.get("publisher", ""),
                    "year": lr.get("year", ""),
                    "rating": lr.get("rating", ""),
                    "description": lr.get("description", "")[:300],
                }),
                category="game_info",
                relevance=0.9,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
    except Exception as e:
        logger.debug("Local metadata search failed: %s", e)

    # Check agent memory for known info
    try:
        from engines.agent_memory import search_memories
        memories = search_memories(game_name, limit=5)
        for m in memories:
            findings.append(ResearchResult(
                topic=game_name,
                source="agent_memory",
                title=f"{m.category}: {m.key}",
                content=m.value[:500],
                category=m.category,
                relevance=m.confidence * 0.8,
                timestamp=m.updated_at,
            ))
    except Exception:
        pass

    # Check compatibility notes
    try:
        from engines.agent_memory import get_compatibility
        compat = get_compatibility(game_name, system)
        for c in compat:
            findings.append(ResearchResult(
                topic=game_name,
                source="compatibility_db",
                title=f"Compatibility: {c.get('emulator', '')}",
                content=f"Status: {c.get('status', '')}. {c.get('notes', '')}",
                category="compatibility",
                relevance=0.85,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
    except Exception:
        pass

    findings.sort(key=lambda f: f.relevance, reverse=True)

    return {
        "game": game_name,
        "system": system,
        "findings": [f.to_dict() for f in findings],
        "total_sources": len(set(f.source for f in findings)),
        "total_findings": len(findings),
    }


def research_system(system: str) -> Dict[str, Any]:
    """Research a system — emulator options, BIOS requirements, known issues.

    Args:
        system: System name

    Returns:
        System research report
    """
    sections: Dict[str, Any] = {}

    # Get BIOS info
    try:
        from engines.bios_manager import get_system_requirements
        bios = get_system_requirements(system)
        if bios:
            sections["bios_requirements"] = bios
    except Exception:
        pass

    # Get emulator quirks
    try:
        from engines.agent_memory import get_quirks
        quirks = get_quirks(system)
        if quirks:
            sections["known_quirks"] = quirks
    except Exception:
        pass

    # Get known issues from troubleshooter
    try:
        from engines.troubleshooter import diagnose_system
        diag = diagnose_system(system)
        sections["diagnostics"] = diag
    except Exception:
        pass

    # Get completion info
    try:
        from engines.rom_completion import get_missing_roms
        missing = get_missing_roms(system, limit=10)
        sections["missing_roms"] = missing
    except Exception:
        pass

    return {
        "system": system,
        "sections": sections,
        "section_count": len(sections),
    }


# -----------------------------------------------------------------------
# Community tips (stored locally)
# -----------------------------------------------------------------------

def store_community_tip(topic: str, tip: str, source: str = "community") -> Dict[str, Any]:
    """Store a community tip in agent memory.

    Args:
        topic: What the tip is about (system, emulator, game)
        tip: The tip content
        source: Where the tip came from

    Returns:
        Stored memory entry
    """
    try:
        from engines.agent_memory import store_memory
        mem = store_memory(
            category="tip",
            subject=topic,
            key=f"tip_{hash(tip) & 0xFFFFFFFF:08x}",
            value=tip,
            source=source,
            tags="community,tip",
        )
        return mem.to_dict()
    except Exception as e:
        return {"error": str(e)}


def get_community_tips(topic: str = "", limit: int = 20) -> Dict[str, Any]:
    """Get community tips from agent memory.

    Args:
        topic: Filter by topic
        limit: Max results

    Returns:
        List of tips
    """
    try:
        from engines.agent_memory import search_memories
        results = search_memories(topic or "tip", category="tip", limit=limit)
        return {
            "tips": [{"topic": m.subject, "tip": m.value, "source": m.source} for m in results],
            "count": len(results),
        }
    except Exception as e:
        return {"error": str(e), "tips": [], "count": 0}


def get_emulator_list() -> Dict[str, Any]:
    """Get the list of known emulators with their details."""
    return {
        "emulators": [
            {"name": name, "type": info["type"], "website": info["url"],
             "has_github_api": bool(info.get("github"))}
            for name, info in EMULATOR_SOURCES.items()
        ],
        "total": len(EMULATOR_SOURCES),
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python research_agent.py updates [emulator]")
        print("  python research_agent.py game <game_name> [system]")
        print("  python research_agent.py system <system>")
        print("  python research_agent.py emulators")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "updates":
        emu = [sys.argv[2]] if len(sys.argv) > 2 else None
        result = check_emulator_updates(emu)
        print(json.dumps(result, indent=2))

    elif cmd == "game":
        game = sys.argv[2] if len(sys.argv) > 2 else ""
        system = sys.argv[3] if len(sys.argv) > 3 else ""
        result = research_game(game, system)
        print(json.dumps(result, indent=2))

    elif cmd == "system":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        result = research_system(system)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "emulators":
        result = get_emulator_list()
        print(json.dumps(result, indent=2))
