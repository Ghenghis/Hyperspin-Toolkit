"""CLI-Anything Bridge — Translates natural language to HyperSpin Extreme Toolkit CLI commands.

CLI-Anything (github.com/HKUDS/CLI-Anything) principle: given a plain-English description
of what you want to do, generate the exact CLI command an agent should execute.

This bridge:
  1. Accepts a natural language task description
  2. Maps it to the correct `python main.py` toolkit command (or MAME/RocketLauncher cmd)
  3. Returns the runnable command string for Goose to execute
  4. Optionally executes directly and returns output

The bridge itself uses the local LLM (LM Studio / Ollama) to handle ambiguous mappings
that the static rule table cannot resolve.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

TOOLKIT_DIR = Path(r"D:\hyperspin_toolkit")
MAIN_PY = str(TOOLKIT_DIR / "main.py")

# ── Static command map — fastest path, no LLM needed ─────────────────
# Keys: lowercase phrase fragments. Values: toolkit CLI templates.
# {system} {path} {id} {query} are filled from extracted entities.
STATIC_MAP: list[tuple[str, str]] = [
    # Audit
    ("audit full",              f"python {MAIN_PY} audit full"),
    ("full audit",              f"python {MAIN_PY} audit full"),
    ("audit everything",        f"python {MAIN_PY} audit full"),
    ("check collection",        f"python {MAIN_PY} audit full"),
    ("collection health",       f"python {MAIN_PY} audit full"),
    ("audit system",            f"python {MAIN_PY} audit system \"{{system}}\""),
    ("check system",            f"python {MAIN_PY} audit system \"{{system}}\""),
    ("health score",            f"python {MAIN_PY} audit full"),
    ("stats",                   f"python {MAIN_PY} stats"),
    ("collection stats",        f"python {MAIN_PY} stats"),
    # Updates / releases
    ("check updates",           f"python {MAIN_PY} releases check"),
    ("update check",            f"python {MAIN_PY} releases check"),
    ("what's new",              f"python {MAIN_PY} releases check"),
    ("outdated emulators",      f"python {MAIN_PY} releases check"),
    ("check mame",              f"python {MAIN_PY} releases check --emulator MAME"),
    ("update mame",             f"python {MAIN_PY} releases check --emulator MAME"),
    ("check dolphin",           f"python {MAIN_PY} releases check --emulator Dolphin"),
    ("check pcsx2",             f"python {MAIN_PY} releases check --emulator PCSX2"),
    ("check rpcs3",             f"python {MAIN_PY} releases check --emulator RPCS3"),
    ("check retroarch",         f"python {MAIN_PY} releases check --emulator RetroArch"),
    ("check emulator",          f"python {MAIN_PY} releases check --emulator \"{{system}}\""),
    # Optimize / space
    ("free up space",           f"python {MAIN_PY} optimize report"),
    ("optimize",                f"python {MAIN_PY} optimize report"),
    ("space report",            f"python {MAIN_PY} optimize report"),
    ("disk usage",              f"python {MAIN_PY} optimize report"),
    ("find duplicates",         f"python {MAIN_PY} optimize duplicates"),
    ("duplicate roms",          f"python {MAIN_PY} optimize duplicates"),
    ("duplicate files",         f"python {MAIN_PY} optimize duplicates"),
    ("redundant emulators",     f"python {MAIN_PY} optimize emulators"),
    ("large files",             f"python {MAIN_PY} optimize report"),
    # Backup
    ("create backup",           f"python {MAIN_PY} backup create \"{{path}}\" --label \"{{label}}\""),
    ("make backup",             f"python {MAIN_PY} backup create \"{{path}}\" --label \"{{label}}\""),
    ("snapshot",                f"python {MAIN_PY} backup create \"{{path}}\" --label \"{{label}}\""),
    ("list backups",            f"python {MAIN_PY} backup list"),
    ("show backups",            f"python {MAIN_PY} backup list"),
    ("rollback",                f"python {MAIN_PY} backup rollback {{id}}"),
    ("restore backup",          f"python {MAIN_PY} backup rollback {{id}}"),
    ("revert",                  f"python {MAIN_PY} backup rollback {{id}}"),
    # Scan
    ("scan roms",               f"python {MAIN_PY} scan roms \"{{system}}\""),
    ("scan system",             f"python {MAIN_PY} scan roms \"{{system}}\""),
    # Tools
    ("discover tools",          f"python {MAIN_PY} tools discover"),
    ("mame version",            f"python {MAIN_PY} tools mame-version"),
    ("installed tools",         f"python {MAIN_PY} tools discover"),
    ("mame xml",                f"python {MAIN_PY} tools mame-listxml --output output\\mame_full.xml"),
    # AI
    ("ask ai",                  f"python {MAIN_PY} ai ask \"{{query}}\""),
    ("analyse audit",           f"python {MAIN_PY} ai analyse --last-audit"),
    ("analyze audit",           f"python {MAIN_PY} ai analyse --last-audit"),
    ("action plan",             f"python {MAIN_PY} ai plan --goal \"{{query}}\""),
    ("what should i do",        f"python {MAIN_PY} ai analyse --last-audit"),
    # Dashboard
    ("dashboard",               f"python {str(TOOLKIT_DIR / 'HyperSpinInventory.py')}"),
    ("generate report",         f"python {str(TOOLKIT_DIR / 'HyperSpinInventory.py')}"),
]

# ── Entity extractor ──────────────────────────────────────────────────

KNOWN_SYSTEMS = [
    "MAME", "Nintendo 64", "Super Nintendo", "NES", "Sega Genesis",
    "PlayStation", "PlayStation 2", "PlayStation 3", "GameCube", "Wii",
    "Dreamcast", "Saturn", "Neo Geo", "Atari 2600", "Game Boy",
    "Game Boy Advance", "Nintendo DS", "PSP", "RetroArch", "Dolphin",
    "PCSX2", "RPCS3", "PPSSPP", "Cemu", "Xenia", "DeSmuME", "mGBA",
]

KNOWN_PATHS = {
    "mame":       r"D:\Arcade\emulators\MAME",
    "emulators":  r"D:\Arcade\emulators",
    "roms":       r"D:\Arcade\ROMs",
    "databases":  r"D:\Arcade\Databases",
    "media":      r"D:\Arcade\HyperSpin\Media",
    "settings":   r"D:\Arcade\RocketLauncher\Settings",
}


def _extract_entities(text: str) -> dict:
    """Extract system name, path, id, query from free-form text."""
    entities: dict[str, str] = {}

    # System name
    text_lower = text.lower()
    for sys in KNOWN_SYSTEMS:
        if sys.lower() in text_lower:
            entities["system"] = sys
            break
    if "system" not in entities:
        # Try to extract quoted system name
        m = re.search(r'"([^"]+)"', text)
        if m:
            entities["system"] = m.group(1)

    # Path
    path_match = re.search(r"[A-Za-z]:\\[^\s,\"]+", text)
    if path_match:
        entities["path"] = path_match.group(0)
    else:
        for key, path in KNOWN_PATHS.items():
            if key in text_lower:
                entities["path"] = path
                break

    # Backup ID
    id_match = re.search(r"\b(bk_\w+|\d{8}_\w+)\b", text)
    if id_match:
        entities["id"] = id_match.group(1)

    # Label (for backups) — use description if no explicit label
    if "label" not in entities:
        # Auto-generate from context
        import datetime
        date_str = datetime.date.today().strftime("%Y%m%d")
        system_part = entities.get("system", "collection").replace(" ", "-")
        entities["label"] = f"auto-{system_part}-{date_str}"

    # Query (for AI commands) — the raw text minus command words
    stop_words = {"audit", "check", "find", "show", "list", "run", "execute",
                  "perform", "do", "create", "make", "get", "tell"}
    words = [w for w in text.split() if w.lower() not in stop_words]
    entities["query"] = " ".join(words) if words else text

    return entities


# ── Core resolution ───────────────────────────────────────────────────

def resolve_command(task_description: str) -> dict:
    """
    Map a natural language task description to a CLI command.

    Returns:
        {
          "command": str,          # runnable command string
          "method":  str,          # "static" | "llm"
          "confidence": float,     # 0.0-1.0
          "entities": dict,        # extracted entities
          "notes": str             # any warnings or notes
        }
    """
    text = task_description.strip()
    text_lower = text.lower()
    entities = _extract_entities(text)

    # 1. Try static map (fast, deterministic)
    best_match: Optional[tuple[str, str]] = None
    best_score = 0
    for phrase, template in STATIC_MAP:
        if phrase in text_lower:
            score = len(phrase)  # longer match = more specific
            if score > best_score:
                best_score = score
                best_match = (phrase, template)

    if best_match:
        _, template = best_match
        try:
            command = template.format(**entities)
            return {
                "command": command,
                "method": "static",
                "confidence": 1.0,
                "entities": entities,
                "notes": "",
            }
        except KeyError as e:
            missing = str(e).strip("'")
            return {
                "command": template,
                "method": "static",
                "confidence": 0.6,
                "entities": entities,
                "notes": f"Missing entity: {missing} — please specify in your request.",
            }

    # 2. Fallback: LLM-assisted resolution
    return _llm_resolve(text, entities)


def _llm_resolve(text: str, entities: dict) -> dict:
    """Use the local LLM to resolve ambiguous commands."""
    try:
        import httpx
        system_prompt = f"""You are a CLI command generator for the HyperSpin Extreme Toolkit.
The toolkit CLI is: python {MAIN_PY} <command>

Available commands:
  audit full
  audit system "<name>"
  releases check [--emulator <name>]
  optimize report
  optimize duplicates
  optimize emulators
  backup create "<path>" --label "<label>"
  backup list
  backup rollback <id>
  scan roms "<system>"
  tools discover
  tools mame-version
  tools mame-listxml --output <file>
  ai ask "<question>"
  ai analyse --last-audit
  ai plan --goal "<goal>"
  stats

Respond with ONLY the exact command to run, nothing else. No explanation."""

        payload = {
            "model": "auto",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": f"Generate the command for: {text}"},
            ],
            "max_tokens": 150,
            "temperature": 0.0,
        }

        r = httpx.post(
            "http://localhost:1234/v1/chat/completions",
            headers={"Authorization": "Bearer lm-studio"},
            json=payload,
            timeout=30.0,
        )
        if r.status_code == 200:
            cmd = r.json()["choices"][0]["message"]["content"].strip()
            cmd = cmd.strip("`").strip()
            return {
                "command": cmd,
                "method": "llm",
                "confidence": 0.85,
                "entities": entities,
                "notes": "LLM-generated — verify before executing.",
            }
    except Exception as exc:
        pass

    return {
        "command": f"python {MAIN_PY} --help",
        "method": "fallback",
        "confidence": 0.0,
        "entities": entities,
        "notes": f"Could not resolve command for: {text!r} — showing help.",
    }


# ── Execution ─────────────────────────────────────────────────────────

def execute_command(command: str, cwd: str = str(TOOLKIT_DIR)) -> dict:
    """Execute a resolved CLI command and return output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "command": command,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out (300s)", "returncode": -1, "command": command}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1, "command": command}


def ask_and_run(task_description: str, auto_execute: bool = False) -> dict:
    """
    Full pipeline: natural language → command → optional execution.

    Args:
        task_description: Plain English description of what to do.
        auto_execute: If True, run the command immediately. If False, return it for review.
    """
    resolved = resolve_command(task_description)

    if not auto_execute or resolved["confidence"] < 0.8:
        resolved["executed"] = False
        resolved["execution_result"] = None
        return resolved

    exec_result = execute_command(resolved["command"])
    resolved["executed"] = True
    resolved["execution_result"] = exec_result
    return resolved


# ── MCP stdio interface (for Goose bridge) ────────────────────────────

def _mcp_stdio_loop():
    """JSON-RPC 2.0 stdio interface — Goose calls this as a subprocess."""
    import sys

    tools = [
        {
            "name": "cli_resolve",
            "description": "Translate a natural language task description into the correct HyperSpin Toolkit CLI command",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Plain English description of what to do"}
                },
                "required": ["task"],
            },
        },
        {
            "name": "cli_run",
            "description": "Resolve AND execute a natural language task against the HyperSpin Toolkit. Confidence >= 0.8 required for auto-execution.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Plain English description of what to do"},
                    "auto_execute": {"type": "boolean", "default": False}
                },
                "required": ["task"],
            },
        },
    ]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method  = req.get("method", "")
        req_id  = req.get("id", 1)
        params  = req.get("params", {})

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cli-anything-bridge", "version": "1.0.0"},
            }}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            task = args.get("task", "")
            if tool_name == "cli_resolve":
                result = resolve_command(task)
            elif tool_name == "cli_run":
                result = ask_and_run(task, auto_execute=args.get("auto_execute", False))
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # CLI mode: python cli_anything_bridge.py "audit MAME"
        task = " ".join(sys.argv[1:])
        result = ask_and_run(task, auto_execute="--run" in sys.argv)
        print(json.dumps(result, indent=2))
    else:
        # MCP stdio mode for Goose
        _mcp_stdio_loop()
