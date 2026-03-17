"""NemoClaw Agents — Specialized sub-agents for the HyperSpin Extreme Toolkit.

NemoClaw is NVIDIA's NeMo-based multi-agent framework. By default it routes to
NVIDIA cloud endpoints. This implementation overrides all inference to use
LOCAL models via LM Studio (OpenAI-compatible) or Ollama — zero cloud dependency.

Architecture:
  Goose (orchestrator) → summon NemoClaw agent → local LLM → execute toolkit tools

Agent Roles:
  - RomSpecialist     ROM validation, hash checking, set completeness analysis
  - EmulatorSpecialist  Emulator health, config, updates, compatibility matrix
  - MediaSpecialist   Artwork, video, wheel quality and coverage analysis
  - DatabaseSpecialist  XML database sync, HyperSpin list management
  - SpaceOptimizer    Disk usage, duplicate detection, archive management
  - UpdateOrchestrator  Multi-emulator update planning and sequencing
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

# ── Local inference endpoints ─────────────────────────────────────────
LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
LMSTUDIO_KEY = "lm-studio"
OLLAMA_URL   = "http://localhost:11434/api/chat"

# Best models per agent role (auto-selected by llm_detector)
AGENT_MODELS = {
    "RomSpecialist":      "lmstudio-community/Devstral-Small-2-24B-Instruct-2512-GGUF/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
    "EmulatorSpecialist": "lmstudio-community/Devstral-Small-2-24B-Instruct-2512-GGUF/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
    "MediaSpecialist":    "lmstudio-community/GLM-4.6V-Flash-GGUF/GLM-4.6V-Flash-Q8_0.gguf",
    "DatabaseSpecialist": "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
    "SpaceOptimizer":     "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
    "UpdateOrchestrator": "eugenehp/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_S.gguf",
}

# Fallback Ollama models if LM Studio not running
AGENT_MODELS_OLLAMA = {
    "RomSpecialist":      "devstral:latest",
    "EmulatorSpecialist": "devstral:latest",
    "MediaSpecialist":    "qwen2.5vl:latest",
    "DatabaseSpecialist": "qwen3:14b",
    "SpaceOptimizer":     "qwen3:8b",
    "UpdateOrchestrator": "qwen3:14b",
}

# Context lengths to request per agent role (tokens)
AGENT_CONTEXT = {
    "RomSpecialist":      65536,   # ROM lists can be large
    "EmulatorSpecialist": 32768,
    "MediaSpecialist":    32768,
    "DatabaseSpecialist": 131072,  # full XML databases
    "SpaceOptimizer":     65536,
    "UpdateOrchestrator": 65536,
}


# ── Agent definitions ─────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_name: str
    task: str
    response: str
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    confidence: float = 1.0
    elapsed_s: float = 0.0
    model_used: str = ""


@dataclass
class NemoAgent:
    name: str
    role: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)

    def invoke(self, task: str, context: str = "") -> AgentResult:
        """Invoke this agent with a task and optional context data."""
        start = time.time()
        messages = [{"role": "system", "content": self.system_prompt}]
        if context:
            messages.append({"role": "user", "content": f"Context data:\n{context}\n\nTask: {task}"})
        else:
            messages.append({"role": "user", "content": task})

        model = AGENT_MODELS.get(self.name, "auto")
        response_text, model_used = _call_lmstudio(messages, model)

        if not response_text:
            model_ollama = AGENT_MODELS_OLLAMA.get(self.name, "qwen3:14b")
            response_text, model_used = _call_ollama(messages, model_ollama)

        if not response_text:
            response_text = "ERROR: No LLM provider available. Start LM Studio or Ollama first."

        elapsed = round(time.time() - start, 2)
        return _parse_agent_response(self.name, task, response_text, elapsed, model_used)

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role, "tools": self.tools}


# ── LLM calls ─────────────────────────────────────────────────────────

def _call_lmstudio(messages: list[dict], model: str) -> tuple[str, str]:
    if not _HAS_HTTPX:
        return "", ""
    try:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.1,
        }
        r = httpx.post(
            LMSTUDIO_URL,
            headers={"Authorization": f"Bearer {LMSTUDIO_KEY}"},
            json=payload,
            timeout=120.0,
        )
        if r.status_code == 200:
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            used = data.get("model", model)
            return text, used
    except Exception:
        pass
    return "", ""


def _call_ollama(messages: list[dict], model: str) -> tuple[str, str]:
    if not _HAS_HTTPX:
        return "", ""
    try:
        payload = {"model": model, "messages": messages, "stream": False}
        r = httpx.post(OLLAMA_URL, json=payload, timeout=120.0)
        if r.status_code == 200:
            text = r.json()["message"]["content"]
            return text, model
    except Exception:
        pass
    return "", ""


def _parse_agent_response(
    agent_name: str, task: str, text: str, elapsed: float, model: str
) -> AgentResult:
    """Extract structured data from agent response."""
    actions, warnings, next_steps = [], [], []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("ACTION:", "- ACTION:")):
            actions.append(stripped.replace("ACTION:", "").replace("- ACTION:", "").strip())
        elif stripped.startswith(("WARNING:", "- WARNING:", "⚠️")):
            warnings.append(stripped.replace("WARNING:", "").replace("- WARNING:", "").replace("⚠️", "").strip())
        elif stripped.startswith(("NEXT:", "- NEXT:", "NEXT STEP:")):
            next_steps.append(stripped.replace("NEXT:", "").replace("- NEXT:", "").replace("NEXT STEP:", "").strip())

    return AgentResult(
        agent_name=agent_name,
        task=task,
        response=text,
        actions=actions,
        warnings=warnings,
        next_steps=next_steps,
        elapsed_s=elapsed,
        model_used=model,
    )


# ── Specialized Agent Definitions ─────────────────────────────────────

ROM_SPECIALIST_PROMPT = """You are the ROM Specialist sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- ROM set validation and completeness analysis
- No-Intro, TOSEC, and MAME ROM naming conventions
- Parent/clone ROM relationships in MAME
- CHD disc image identification
- ROM hash verification (CRC32, MD5, SHA1)
- Missing ROM diagnosis and resolution paths
- ROM set migration between emulator versions

Collection facts:
- Root: D:\\Arcade\\
- ROM directories: D:\\Arcade\\ROMs\\<SYSTEM>\\
- 184 systems managed via HyperSpin + RocketLauncher
- MAME currently 0.228 (severely behind latest 0.273+)
- Total collection ~12 TB, ~60 GB free

Response format:
- Start with a direct answer
- List ACTION: items for concrete steps Goose should execute
- List WARNING: items for risks
- List NEXT: items for follow-up steps

Always recommend the toolkit command: python D:\\hyperspin_toolkit\\main.py <cmd>
Never modify files directly — only recommend toolkit commands."""

EMULATOR_SPECIALIST_PROMPT = """You are the Emulator Specialist sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- Emulator compatibility matrices (what emulator runs what games best)
- Emulator configuration and INI settings
- RocketLauncher module configuration
- Emulator version management and safe upgrade procedures
- Known bugs and fixes for each emulator version
- Performance tuning for RTX 3090 Ti (24 GB VRAM) + Windows 11

Installed emulators: D:\\Arcade\\emulators\\ (173 installed)
RocketLauncher: D:\\Arcade\\RocketLauncher\\
MAME: version 0.228 installed, 0.273 available (major gap)

Response format:
- Direct answer first
- ACTION: lines for Goose to execute via toolkit
- WARNING: lines for risks (especially before overwriting working emulators)
- NEXT: follow-up steps

Key rule: ALWAYS recommend side-by-side install, never overwrite working emulator."""

MEDIA_SPECIALIST_PROMPT = """You are the Media Specialist sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- HyperSpin media structure (Wheel, Images/Artwork1-4, Backgrounds, Marquees, Screenshots, Snaps, Video, Themes)
- Artwork quality assessment (resolution, format, transparency, orientation)
- Scraping tools: Skyscraper, EmuMovies, HyperSpin FTP, LaunchBox
- Video preview formats and encoding standards
- Wheel logo conventions (PNG, transparent background, 400px+ width)
- Media coverage analysis and gap identification

Media root: D:\\Arcade\\HyperSpin\\Media\\<SYSTEM>\\
421 media directories across 184 systems

Vision model available: GLM-4.6V-Flash (local, RTX 3090 Ti)
For image analysis tasks, recommend: python D:\\hyperspin_toolkit\\main.py ai vision <path>

Response format:
- Direct answer
- ACTION: concrete steps
- WARNING: quality issues found
- NEXT: scraping or fix recommendations"""

DATABASE_SPECIALIST_PROMPT = """You are the Database Specialist sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- HyperSpin XML database format and structure
- Game list management (adding, removing, updating entries)
- XML validation and repair
- Database synchronisation with ROM sets
- MAME -listxml processing and filtering
- No-Intro and TOSEC database imports
- RocketLauncher database integration

Database root: D:\\Arcade\\Databases\\ (422 XML files)
Format: HyperSpin XML — <game name="..."><description>...</description>...</game>

Toolkit database commands:
  python D:\\hyperspin_toolkit\\main.py audit system "<SYSTEM>"
  python D:\\hyperspin_toolkit\\main.py tools mame-listxml --hyperspin --output <file>

Response format:
- Direct answer with XML context where relevant
- ACTION: toolkit commands to run
- WARNING: data integrity risks
- NEXT: verification steps"""

SPACE_OPTIMIZER_PROMPT = """You are the Space Optimizer sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- Disk space analysis and recovery prioritisation
- Duplicate file detection by hash (not just name)
- Archive management (zip, 7z, CHD)
- Orphaned media identification
- Redundant emulator version cleanup
- Storage efficiency recommendations

Critical: Only ~60 GB free on 12 TB drive. Space is CRITICAL.

Toolkit space commands:
  python D:\\hyperspin_toolkit\\main.py optimize report
  python D:\\hyperspin_toolkit\\main.py optimize duplicates
  python D:\\hyperspin_toolkit\\main.py optimize emulators

Space recovery priority:
1. Duplicate ROMs (largest gain, 50-200 GB potential)
2. Extracted + still-zipped archives (double-stored)
3. Redundant emulator copies (5-30 GB)
4. Orphaned media files (5-50 GB)
5. Old backup files > 30 days

Response format:
- Quantified space recovery estimates first
- ACTION: commands with expected space gain
- WARNING: files that must not be deleted
- NEXT: verification after deletion"""

UPDATE_ORCHESTRATOR_PROMPT = """You are the Update Orchestrator sub-agent for the HyperSpin Extreme Toolkit.

Your expertise:
- Multi-emulator update sequencing and dependency management
- Safe update pipeline: backup → download → side-by-side install → test → commit/rollback
- GitHub release monitoring for 20+ emulators
- Version compatibility assessment
- Risk scoring for each update (impact vs breaking chance)
- Space planning for batch updates

Current state:
- 173 emulators at D:\\Arcade\\emulators\\
- ~60 GB free — must plan space carefully for batch updates
- MAME 0.228 → 0.273: highest priority, 45 versions behind
- PCSX2 1.7.x → 2.3.x: major UI + compatibility improvements

Toolkit update commands:
  python D:\\hyperspin_toolkit\\main.py releases check
  python D:\\hyperspin_toolkit\\main.py releases check --emulator <NAME>
  python D:\\hyperspin_toolkit\\main.py backup create "<path>" --label "<label>"

Response format:
- Prioritised update plan (order by impact × safety)
- ACTION: exact commands in correct sequence
- WARNING: breaking changes or space concerns
- NEXT: post-update verification steps"""


# ── Agent Registry ────────────────────────────────────────────────────

def create_agents() -> dict[str, NemoAgent]:
    return {
        "RomSpecialist": NemoAgent(
            name="RomSpecialist",
            role="ROM validation, set completeness, hash verification, MAME ROM management",
            system_prompt=ROM_SPECIALIST_PROMPT,
            tools=["audit_system", "find_duplicates", "scan_roms", "mame_version"],
        ),
        "EmulatorSpecialist": NemoAgent(
            name="EmulatorSpecialist",
            role="Emulator health, config, upgrade planning, RocketLauncher integration",
            system_prompt=EMULATOR_SPECIALIST_PROMPT,
            tools=["audit_full", "check_emulator_update", "discover_tools", "backup_create"],
        ),
        "MediaSpecialist": NemoAgent(
            name="MediaSpecialist",
            role="HyperSpin media quality, coverage analysis, scraping recommendations",
            system_prompt=MEDIA_SPECIALIST_PROMPT,
            tools=["audit_system", "get_stats", "vision_analyse"],
        ),
        "DatabaseSpecialist": NemoAgent(
            name="DatabaseSpecialist",
            role="HyperSpin XML databases, game list management, MAME XML generation",
            system_prompt=DATABASE_SPECIALIST_PROMPT,
            tools=["audit_system", "mame_listxml", "audit_full"],
        ),
        "SpaceOptimizer": NemoAgent(
            name="SpaceOptimizer",
            role="Disk usage analysis, duplicate detection, archive cleanup",
            system_prompt=SPACE_OPTIMIZER_PROMPT,
            tools=["optimize_report", "find_duplicates", "find_redundant_emulators", "find_large_files", "disk_usage"],
        ),
        "UpdateOrchestrator": NemoAgent(
            name="UpdateOrchestrator",
            role="Multi-emulator update sequencing, risk scoring, safe pipeline management",
            system_prompt=UPDATE_ORCHESTRATOR_PROMPT,
            tools=["check_all_updates", "check_emulator_update", "backup_create", "get_stats"],
        ),
    }


AGENTS = create_agents()


# ── Routing — select best agent for a task ────────────────────────────

ROUTING_KEYWORDS: dict[str, list[str]] = {
    "RomSpecialist":      ["rom", "roms", "hash", "crc", "sha", "chd", "parent", "clone", "no-intro", "tosec", "missing rom", "wrong rom"],
    "EmulatorSpecialist": ["emulator", "mame", "dolphin", "pcsx2", "rpcs3", "ppsspp", "cemu", "retroarch", "config", "ini", "rocketlauncher", "module"],
    "MediaSpecialist":    ["media", "artwork", "wheel", "marquee", "screenshot", "snap", "video", "theme", "image", "art", "scrape", "cover"],
    "DatabaseSpecialist": ["database", "xml", "game list", "gamelist", "listxml", "hsl", "entry", "description"],
    "SpaceOptimizer":     ["space", "disk", "duplicate", "storage", "free", "large file", "archive", "zip", "7z", "redundant", "cleanup", "clean up"],
    "UpdateOrchestrator": ["update", "upgrade", "version", "release", "latest", "new version", "github", "changelog", "batch update", "all emulators"],
}


def route_task(task: str) -> NemoAgent:
    """Select the most appropriate agent for a given task."""
    task_lower = task.lower()
    scores: dict[str, int] = {name: 0 for name in AGENTS}
    for agent_name, keywords in ROUTING_KEYWORDS.items():
        for kw in keywords:
            if kw in task_lower:
                scores[agent_name] += len(kw)  # longer keyword = higher specificity

    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        best = "EmulatorSpecialist"  # default
    return AGENTS[best]


# ── Multi-agent orchestration ─────────────────────────────────────────

def delegate(task: str, context: str = "", agent_name: Optional[str] = None) -> AgentResult:
    """
    Route a task to the best NemoClaw agent and return its result.

    Args:
        task: Natural language task description
        context: Optional JSON/text context data to include
        agent_name: Force a specific agent (skip routing)
    """
    agent = AGENTS.get(agent_name) if agent_name else route_task(task)
    return agent.invoke(task, context)


def multi_agent_plan(goal: str, context: str = "") -> list[AgentResult]:
    """
    Execute a complex goal using multiple agents in sequence.
    Returns a list of results from each agent consulted.
    """
    goal_lower = goal.lower()
    results = []

    # Determine which agents are relevant for this goal
    selected: list[str] = []
    for agent_name, keywords in ROUTING_KEYWORDS.items():
        if any(kw in goal_lower for kw in keywords):
            selected.append(agent_name)

    if not selected:
        selected = ["EmulatorSpecialist", "SpaceOptimizer"]

    # Always include UpdateOrchestrator for multi-step plans
    if "UpdateOrchestrator" not in selected and len(selected) > 1:
        selected.append("UpdateOrchestrator")

    for agent_name in selected:
        agent = AGENTS[agent_name]
        result = agent.invoke(
            f"As part of the overall goal: '{goal}'\nYour specific role: {agent.role}\nProvide your recommendations.",
            context,
        )
        results.append(result)

    return results


# ── MCP stdio interface for Goose ─────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "name": "nemoclaw_delegate",
        "description": "Delegate a HyperSpin task to the best NemoClaw specialist agent (ROM, Emulator, Media, Database, Space, Update). The agent uses the local LLM to reason about the task and returns concrete toolkit commands to execute.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task":       {"type": "string", "description": "Task description in plain English"},
                "context":    {"type": "string", "description": "Optional context data (audit JSON, release check output, etc.)"},
                "agent_name": {"type": "string", "description": "Force a specific agent: RomSpecialist, EmulatorSpecialist, MediaSpecialist, DatabaseSpecialist, SpaceOptimizer, UpdateOrchestrator"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "nemoclaw_plan",
        "description": "Run a complex multi-step goal through multiple NemoClaw specialist agents simultaneously and return a consolidated action plan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal":    {"type": "string", "description": "High-level goal, e.g. 'update all emulators and clean up 100GB of space'"},
                "context": {"type": "string", "description": "Optional context data"},
            },
            "required": ["goal"],
        },
    },
    {
        "name": "nemoclaw_list_agents",
        "description": "List all available NemoClaw specialist agents, their roles, and what tasks they handle.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _mcp_stdio_loop():
    import sys
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
                "serverInfo": {"name": "nemoclaw-agents", "version": "1.0.0"},
            }}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_SCHEMA}}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            if tool_name == "nemoclaw_delegate":
                result = delegate(args.get("task", ""), args.get("context", ""), args.get("agent_name"))
                text = json.dumps(asdict(result), indent=2)
            elif tool_name == "nemoclaw_plan":
                results = multi_agent_plan(args.get("goal", ""), args.get("context", ""))
                text = json.dumps([asdict(r) for r in results], indent=2)
            elif tool_name == "nemoclaw_list_agents":
                text = json.dumps({name: ag.to_dict() for name, ag in AGENTS.items()}, indent=2)
            else:
                text = json.dumps({"error": f"Unknown tool: {tool_name}"})
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": text}]
            }}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        result = delegate(task)
        print(json.dumps(asdict(result), indent=2))
    else:
        _mcp_stdio_loop()
