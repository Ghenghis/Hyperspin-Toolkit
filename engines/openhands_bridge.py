"""OpenHands Bridge — Connects Goose to the OpenHands autonomous agent via REST API.

OpenHands (formerly OpenDevin) runs as a local server (Docker or standalone).
Default port: 3000. Goose delegates complex multi-file operations, code edits,
and browsing tasks here, then receives structured results back.

OpenHands capabilities Goose delegates TO it:
  - Multi-file code edits (e.g. update all RocketLauncher .ini files at once)
  - Shell command sequences with live feedback
  - Browser automation (scraping, EmuMovies login, ROM site navigation)
  - Git operations on the toolkit repo
  - Complex Python script generation and execution

Integration modes:
  A. HTTP API  — OpenHands server running at http://localhost:3000
  B. MCP stdio — this file acts as Goose stdio extension bridge
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

OPENHANDS_BASE = "http://localhost:3000"
TOOLKIT_DIR    = Path(r"D:\hyperspin_toolkit")

# ── OpenHands REST client ─────────────────────────────────────────────

class OpenHandsClient:
    """Minimal REST client for OpenHands server."""

    def __init__(self, base_url: str = OPENHANDS_BASE):
        self.base = base_url.rstrip("/")
        self._session_id: Optional[str] = None

    def is_running(self) -> bool:
        if not _HAS_HTTPX:
            return False
        try:
            r = httpx.get(f"{self.base}/api/options/models", timeout=3.0)
            return r.status_code in (200, 401)
        except Exception:
            return False

    def get_version(self) -> Optional[str]:
        if not _HAS_HTTPX:
            return None
        try:
            r = httpx.get(f"{self.base}/api/version", timeout=3.0)
            if r.status_code == 200:
                return r.json().get("version")
        except Exception:
            pass
        return None

    def new_conversation(self, initial_message: str, model: str = "local") -> dict:
        """Start a new OpenHands conversation/session."""
        if not _HAS_HTTPX:
            return {"error": "httpx not installed"}
        sid = str(uuid.uuid4())
        try:
            payload = {
                "initial_user_msg": initial_message,
                "session_id": sid,
                "llm_config": {
                    "model": model,
                    "base_url": "http://localhost:1234/v1",
                    "api_key": "lm-studio",
                },
            }
            r = httpx.post(
                f"{self.base}/api/conversations",
                json=payload,
                timeout=30.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                self._session_id = data.get("conversation_id", sid)
                return {"ok": True, "session_id": self._session_id, "data": data}
            return {"error": r.text, "status": r.status_code}
        except Exception as exc:
            return {"error": str(exc)}

    def send_message(self, message: str, session_id: Optional[str] = None) -> dict:
        """Send a follow-up message to an active session."""
        if not _HAS_HTTPX:
            return {"error": "httpx not installed"}
        sid = session_id or self._session_id
        if not sid:
            return {"error": "No active session. Call new_conversation first."}
        try:
            r = httpx.post(
                f"{self.base}/api/conversations/{sid}/messages",
                json={"content": message},
                timeout=120.0,
            )
            if r.status_code == 200:
                return {"ok": True, "data": r.json()}
            return {"error": r.text, "status": r.status_code}
        except Exception as exc:
            return {"error": str(exc)}

    def get_events(self, session_id: Optional[str] = None, start_id: int = 0) -> dict:
        """Poll for events/results from an active session."""
        if not _HAS_HTTPX:
            return {"error": "httpx not installed"}
        sid = session_id or self._session_id
        if not sid:
            return {"error": "No active session"}
        try:
            r = httpx.get(
                f"{self.base}/api/conversations/{sid}/events",
                params={"start_id": start_id},
                timeout=30.0,
            )
            if r.status_code == 200:
                return {"ok": True, "events": r.json()}
            return {"error": r.text}
        except Exception as exc:
            return {"error": str(exc)}

    def wait_for_completion(
        self,
        session_id: Optional[str] = None,
        timeout: int = 300,
        poll_interval: float = 2.0,
    ) -> dict:
        """Poll until the agent finishes or timeout."""
        sid = session_id or self._session_id
        start = time.time()
        last_event_id = 0
        all_events: list[dict] = []

        while time.time() - start < timeout:
            result = self.get_events(sid, last_event_id)
            if "error" in result:
                return result

            events = result.get("events", [])
            if events:
                all_events.extend(events)
                last_event_id = events[-1].get("id", last_event_id) + 1

                # Check for completion event
                for ev in events:
                    if ev.get("type") in ("agent_state_changed",) and \
                       ev.get("extras", {}).get("agent_state") in ("finished", "error", "stopped"):
                        return {
                            "ok": True,
                            "completed": True,
                            "events": all_events,
                            "final_state": ev.get("extras", {}).get("agent_state"),
                        }

            time.sleep(poll_interval)

        return {"ok": True, "completed": False, "timeout": True, "events": all_events}

    def run_task(self, task: str, timeout: int = 300) -> dict:
        """Full pipeline: start session → wait for completion → return results."""
        if not self.is_running():
            return {
                "error": "OpenHands is not running.",
                "fix": "Start OpenHands: docker run -it -p 3000:3000 docker.all-hands.dev/all-hands-ai/runtime:latest",
                "alternative": "Use the toolkit directly via CLI: python D:\\hyperspin_toolkit\\main.py",
            }

        conv = self.new_conversation(task)
        if "error" in conv:
            return conv

        sid = conv["session_id"]
        result = self.wait_for_completion(sid, timeout=timeout)
        result["session_id"] = sid
        result["task"] = task
        return result


# ── High-level toolkit operations for OpenHands ───────────────────────

CLIENT = OpenHandsClient()


def edit_rocketlauncher_ini(system: str, key: str, value: str) -> dict:
    """Update a RocketLauncher INI setting for a system via OpenHands."""
    task = f"""Edit the RocketLauncher settings file for system "{system}".
File: D:\\Arcade\\RocketLauncher\\Settings\\{system}\\{system}.ini
Change key "{key}" to value "{value}".
Verify the file exists before editing. Report the change made."""
    return CLIENT.run_task(task)


def batch_update_emulator_paths(old_path: str, new_path: str) -> dict:
    """Update emulator path across all RocketLauncher INI files."""
    task = f"""Search all .ini files under D:\\Arcade\\RocketLauncher\\Settings\\ for the path:
  {old_path}
Replace every occurrence with:
  {new_path}
Report: how many files were changed, which files, what lines were modified.
Do NOT change any other settings."""
    return CLIENT.run_task(task, timeout=120)


def generate_mame_hyperspin_xml(mame_xml_path: str, roms_dir: str, output_path: str) -> dict:
    """Generate a HyperSpin-compatible XML from MAME -listxml output."""
    task = f"""Parse the MAME -listxml output at: {mame_xml_path}
Filter to only games that have ROM files present in: {roms_dir}
Generate a HyperSpin-compatible XML database at: {output_path}

HyperSpin XML format:
<?xml version="1.0"?>
<menu>
  <header>
    <listname>MAME</listname>
    <lastlistupdate>YYYY-MM-DD</lastlistupdate>
    <listversion>15.1</listversion>
    <exporterversion>Export: Unity v1.0</exporterversion>
  </header>
  <game name="pacman">
    <description>Pac-Man (Midway)</description>
    <cloneof></cloneof>
    <crc></crc>
    <manufacturer>Namco</manufacturer>
    <year>1980</year>
    <genre>Maze</genre>
    <rating>Not Rated</rating>
    <enabled>Yes</enabled>
  </game>
</menu>

Report: total games in MAME XML, games with ROMs present, games in output."""
    return CLIENT.run_task(task, timeout=600)


def analyse_rom_directory(system: str, roms_path: str) -> dict:
    """Analyse a ROM directory and report statistics."""
    task = f"""Analyse the ROM directory for system "{system}" at: {roms_path}
Report:
1. Total file count by extension (.zip, .7z, .chd, .iso, .bin, .cue, etc.)
2. Total size in GB
3. Any obviously corrupted or zero-byte files
4. Files that don't match the expected naming convention for {system}
5. Duplicate filenames (same name, different extension)
Output as structured JSON."""
    return CLIENT.run_task(task, timeout=120)


def fix_broken_emulator_config(emulator_name: str, emulator_path: str) -> dict:
    """Diagnose and fix a broken emulator configuration."""
    task = f"""Diagnose the {emulator_name} installation at: {emulator_path}
Steps:
1. Check the executable exists and is not zero bytes
2. Check the main config file exists and is valid
3. Check all referenced paths in the config actually exist
4. List any obviously wrong settings (wrong paths, missing directories)
5. Suggest or apply minimal fixes to get it working
Report each issue found and the fix applied."""
    return CLIENT.run_task(task, timeout=120)


# ── MCP stdio interface for Goose ─────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "name": "openhands_status",
        "description": "Check if the OpenHands server is running and get its version.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "openhands_run_task",
        "description": "Delegate a complex multi-file or code-heavy task to the OpenHands autonomous agent. Use this for tasks that require reading/writing multiple files, running shell sequences, or browser automation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task":    {"type": "string", "description": "Detailed task description for OpenHands"},
                "timeout": {"type": "integer", "description": "Max seconds to wait (default 300)", "default": 300},
            },
            "required": ["task"],
        },
    },
    {
        "name": "openhands_update_ini",
        "description": "Update a RocketLauncher INI setting for a specific system.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "system": {"type": "string"},
                "key":    {"type": "string"},
                "value":  {"type": "string"},
            },
            "required": ["system", "key", "value"],
        },
    },
    {
        "name": "openhands_batch_paths",
        "description": "Update an emulator path across ALL RocketLauncher INI files (e.g. after renaming emulator directory).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "old_path": {"type": "string"},
                "new_path": {"type": "string"},
            },
            "required": ["old_path", "new_path"],
        },
    },
    {
        "name": "openhands_analyse_roms",
        "description": "Analyse a ROM directory structure and return detailed statistics.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "system":    {"type": "string"},
                "roms_path": {"type": "string"},
            },
            "required": ["system", "roms_path"],
        },
    },
]


def _dispatch(tool_name: str, args: dict) -> str:
    if tool_name == "openhands_status":
        running = CLIENT.is_running()
        version = CLIENT.get_version() if running else None
        return json.dumps({
            "running": running,
            "version": version,
            "url": OPENHANDS_BASE,
            "start_command": "docker run -it -p 3000:3000 -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest docker.all-hands.dev/all-hands-ai/openhands:latest",
        }, indent=2)
    elif tool_name == "openhands_run_task":
        r = CLIENT.run_task(args.get("task", ""), timeout=args.get("timeout", 300))
        return json.dumps(r, indent=2, default=str)
    elif tool_name == "openhands_update_ini":
        r = edit_rocketlauncher_ini(args["system"], args["key"], args["value"])
        return json.dumps(r, indent=2, default=str)
    elif tool_name == "openhands_batch_paths":
        r = batch_update_emulator_paths(args["old_path"], args["new_path"])
        return json.dumps(r, indent=2, default=str)
    elif tool_name == "openhands_analyse_roms":
        r = analyse_rom_directory(args["system"], args["roms_path"])
        return json.dumps(r, indent=2, default=str)
    return json.dumps({"error": f"Unknown tool: {tool_name}"})


def _mcp_stdio_loop():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        req_id = req.get("id", 1)
        params = req.get("params", {})

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "openhands-bridge", "version": "1.0.0"},
            }}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}
        elif method == "tools/call":
            text = _dispatch(params.get("name", ""), params.get("arguments", {}))
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": text}]
            }}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        print(json.dumps({"running": CLIENT.is_running(), "version": CLIENT.get_version()}, indent=2))
    elif len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        print(json.dumps(CLIENT.run_task(task), indent=2, default=str))
    else:
        _mcp_stdio_loop()
