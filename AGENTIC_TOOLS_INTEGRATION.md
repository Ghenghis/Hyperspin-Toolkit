# Agentic Tools Integration — Goose + OpenHands + CLI-Anything + NemoClaw

## BUILT STATUS: FULLY INTEGRATED (2026-03)

All four systems are wired end-to-end. Zero cloud. All inference local via LM Studio on RTX 3090 Ti.

---

## Final Architecture

```
USER (natural language)
        ↓
┌────────────────────────────────────────────────────────────────┐
│  GOOSE  (orchestrator)                                         │
│  Provider: LM Studio  →  http://localhost:1234/v1             │
│  Model:    Devstral-Small-2-24B Q4_K_M  (13.35 GB, 32K ctx)  │
│  Fallback: Qwen3.5-27B Opus 4.6 (128K→256K ctx)              │
│  Config:   %APPDATA%\Block\goose\config\config.yaml           │
│  Skills:   11x hyperspin-* SKILL.md files loaded              │
└──────┬────────────┬────────────┬────────────┬─────────────────┘
       │            │            │            │
┌──────▼──────┐ ┌───▼────────┐ ┌▼──────────┐ ┌▼────────────────┐
│ HyperSpin   │ │CLI-Anything│ │ NemoClaw  │ │  OpenHands      │
│ Toolkit MCP │ │  Bridge    │ │  Agents   │ │  Bridge         │
│             │ │            │ │           │ │                 │
│ 13 MCP tools│ │NL→CLI cmd  │ │ 6 roles   │ │REST→localhost   │
│ audit_full  │ │cli_resolve │ │ specialist│ │:3000            │
│ backup_*    │ │cli_run     │ │ sub-agents│ │                 │
│ optimize_*  │ │            │ │ local LLM │ │ multi-file ops  │
│ releases_*  │ │            │ │           │ │ batch INI edits │
│ mame_*      │ │            │ │           │ │ browser auto    │
└──────┬──────┘ └───┬────────┘ └┬──────────┘ └┬────────────────┘
       │            │            │              │
       └────────────┴────────────┴──────────────┘
                          ↓
         D:\hyperspin_toolkit\  (Python CLI engine)
         D:\Arcade\             (12 TB collection)
         LM Studio @ localhost:1234/v1
         Ollama @ localhost:11434  (fallback)
```

## Files Built

### Engine Bridges
| File                             | Purpose                                                      |
| -------------------------------- | ------------------------------------------------------------ |
| `engines/cli_anything_bridge.py` | NL→CLI translation, static map + LLM fallback, MCP stdio     |
| `engines/nemoclaw_agents.py`     | 6 NemoClaw specialist agents, all using local LLM, MCP stdio |
| `engines/openhands_bridge.py`    | OpenHands REST client + 5 MCP tools for file/code delegation |
| `engines/llm_detector.py`        | VRAM-aware model scanner, 128K-256K context window data      |

### Goose Skills (11 total in `%APPDATA%\Block\goose\config\skills\`)
| Skill                    | Covers                                               |
| ------------------------ | ---------------------------------------------------- |
| `hyperspin-toolkit`      | Master overview, all commands, model table           |
| `hyperspin-audit`        | Full and single-system audit workflows               |
| `hyperspin-update`       | Safe emulator update pipeline                        |
| `hyperspin-optimize`     | Space recovery, duplicates, orphaned media           |
| `hyperspin-backup`       | Versioned backups, rollback procedures               |
| `hyperspin-releases`     | GitHub release checking, 20+ emulators tracked       |
| `hyperspin-mame`         | MAME 0.228→0.273 upgrade, ROM set migration, repair  |
| `hyperspin-ai`           | Local LLM assistant, large context usage guide       |
| `hyperspin-vision`       | GLM-4.6V-Flash media/screenshot analysis             |
| `hyperspin-orchestrator` | **Master skill — all 4 agents working together**     |
| `hyperspin-cli-anything` | CLI-Anything usage, confidence scoring, safety rules |

### Config Changes Applied
| File                                       | Change                                                                                                                                                                     |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `%APPDATA%\Block\goose\config\config.yaml` | Added `hyperspin_toolkit`, `cli_anything`, `nemoclaw_agents` extensions; wired `openhands_bridge`; switched provider to `lmstudio`; model = Devstral-24B; context = 131072 |
| `C:\Users\Admin\.lmstudio\mcp.json`        | Added `hyperspin-toolkit`, `nemoclaw-agents`, `cli-anything`, `openhands` MCP servers; expanded filesystem to include `D:\Arcade`                                          |
| `C:\Users\Admin\.lmstudio\settings.json`   | `defaultContextLength` 8196 → **131072** (unlocks 128K for Qwen3.5)                                                                                                        |

### Setup Scripts
| Script                    | Purpose                                                   |
| ------------------------- | --------------------------------------------------------- |
| `setup/goose_setup.py`    | One-shot E2E validator + auto-fixer for entire stack      |
| `setup/install_goose.ps1` | Downloads Goose v1.27.2 from GitHub, installs + validates |

## NemoClaw Agent Roles (local LLM, NOT NVIDIA cloud)

| Agent                | LM Studio Model      | Handles                                              |
| -------------------- | -------------------- | ---------------------------------------------------- |
| `RomSpecialist`      | Devstral-24B         | ROM validation, hashing, MAME parent/clone           |
| `EmulatorSpecialist` | Devstral-24B         | Config, RocketLauncher modules, upgrade planning     |
| `MediaSpecialist`    | GLM-4.6V-Flash       | Artwork quality, coverage analysis, scraping advice  |
| `DatabaseSpecialist` | Qwen3.5-9B Opus 4.6  | HyperSpin XML, game list sync, MAME listxml          |
| `SpaceOptimizer`     | Qwen3.5-9B Opus 4.6  | Duplicate detection, archive cleanup, space recovery |
| `UpdateOrchestrator` | Qwen3.5-27B Opus 4.6 | Multi-emulator batch update sequencing, risk scoring |

## OpenHands Integration

OpenHands (formerly OpenDevin) runs at `http://localhost:3000`.
Goose delegates to it via `openhands_bridge` for:
- Batch updating all RocketLauncher INI files after emulator rename
- Generating filtered HyperSpin XML from MAME -listxml output
- Multi-file config repairs across 173 emulator directories
- Browser automation for scraping media/updates

Start OpenHands:
```powershell
docker run -it -p 3000:3000 `
  -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest `
  docker.all-hands.dev/all-hands-ai/openhands:latest
```

## LM Studio Context Windows (RTX 3090 Ti, 24 GB VRAM)

| Model                       | Size     | Native | RoPE Max | VRAM @ 128K    |
| --------------------------- | -------- | ------ | -------- | -------------- |
| Devstral-24B Q4_K_M         | 13.35 GB | 32K    | 32K      | —              |
| Qwen3.5-9B Q8 Opus 4.6      | 9.77 GB  | 128K   | **256K** | ~13 GB total   |
| Qwen3.5-27B Q4_K_S Opus 4.6 | 14.52 GB | 128K   | **256K** | ~19 GB total   |
| Qwen3.5-35B A3B Q4_K_M      | 19.72 GB | 128K   | **256K** | ~24 GB (tight) |
| GLM-4.6V-Flash Q8           | 9.31 GB  | 128K   | 128K     | ~11 GB total   |

`defaultContextLength` in LM Studio settings is now **131072** (128K). For 256K, set to `262144`.

## Run Validation

```powershell
# Full stack check
python D:\hyperspin_toolkit\setup\goose_setup.py --e2e

# Quick bridge test (each bridge must respond to tools/list)
python D:\hyperspin_toolkit\engines\cli_anything_bridge.py "audit MAME"
python D:\hyperspin_toolkit\engines\nemoclaw_agents.py "list agents"
python D:\hyperspin_toolkit\engines\openhands_bridge.py status
```

---

## Original Research Notes (preserved below)

### Verdict Table

| Tool                         | Useful?            | Why                                                            | Integration Priority |
| ---------------------------- | ------------------ | -------------------------------------------------------------- | -------------------- |
| **Goose** (Block)            | **YES — CRITICAL** | Open-source AI agent, local LLM, MCP extensions, CLI + desktop | **BUILT**            |
| **CLI-Anything** (HKUDS)     | **YES — HIGH**     | NL→CLI translation for toolkit, MAME, RocketLauncher           | **BUILT**            |
| **OpenHands** (All Hands AI) | **YES — HIGH**     | Autonomous multi-file agent, batch INI updates, browser        | **BUILT**            |
| **NemoClaw** (NVIDIA)        | **YES — MEDIUM**   | Specialist sub-agents — configured for LOCAL LLM, not cloud    | **BUILT**            |
| **OpenShell** (NVIDIA)       | **SKIP**           | Requires Docker+K3s, routes to NVIDIA cloud                    | **NOT USED**         |

---

## Tool 1: Goose (Block) — The Agent Runtime

### What It Is
Goose is an **open-source, extensible AI agent** by Block (formerly Square) that goes beyond code suggestions. It can install, execute, edit, and test — autonomously. It works with **any LLM** including Ollama locally.

### Key Capabilities
- **Works with Ollama locally** — full offline, private operation
- **MCP server integration** — extends capabilities via Model Context Protocol
- **Multi-model support** — use different models for different tasks (cheap model for simple, powerful for complex)
- **CLI + Desktop app** — both interfaces available
- **Extensions ecosystem** — community extensions for file management, web scraping, database operations
- **Structured outputs** — reliable JSON from local models for programmatic use
- **Session management** — persistent context across interactions

### Why It Helps Our Toolkit
1. **Autonomous emulator management** — Goose can execute our toolkit commands, check results, and iterate
2. **ROM audit automation** — can run audits, interpret results, and suggest fixes
3. **Update orchestration** — can manage the snapshot→update→test→rollback pipeline end-to-end
4. **Natural language interface** — users ask in plain English, Goose translates to toolkit commands
5. **MCP bridge** — our toolkit can expose its APIs as MCP tools that Goose natively consumes

### Installation (Windows)
```powershell
# Option A: Installer (recommended)
# Download from: https://github.com/block/goose/releases/tag/v1.27.2
# Run the Windows installer (.msi or .exe)

# Option B: Via npm
npm install -g @anthropic-ai/goose

# Option C: Via cargo (Rust)
cargo install goose-cli
```

### Configure with Ollama (Local LLM)
```yaml
# ~/.config/goose/profiles.yaml
default:
  provider: ollama
  model: llama3.1:8b
  # or for better code tasks:
  # model: deepseek-coder-v2:16b
```

Or configure interactively:
```bash
goose configure
# Select provider: ollama
# Select model: llama3.1:8b
# Base URL: http://localhost:11434
```

### Configure with LM Studio
```yaml
default:
  provider: openai  # LM Studio uses OpenAI-compatible API
  model: local-model
  base_url: http://localhost:1234/v1
  api_key: lm-studio  # any non-empty string
```

### Expose Our Toolkit as MCP Tools for Goose
```json
// .goose/mcp-servers.json
{
  "hyperspin-toolkit": {
    "command": "python",
    "args": ["D:\\hyperspin_toolkit\\mcp_bridge.py"],
    "env": {
      "TOOLKIT_CONFIG": "D:\\hyperspin_toolkit\\config.yaml"
    }
  }
}
```

### Example Goose Sessions with Our Toolkit
```
User: "Check if any emulators have updates available"
Goose: [runs: python main.py releases check]
       [parses output, formats summary]
       "Found 8 emulators with available updates:
        - MAME: 0.228 → 0.273 (critical)
        - PCSX2: 1.40 → 2.3.x (major upgrade)
        ..."

User: "Upgrade MAME safely"
Goose: [runs: python main.py backup create D:\Arcade\emulators\MAME --label pre-upgrade]
       [downloads latest MAME from GitHub]
       [extracts side-by-side]
       [runs ROM audit]
       [reports findings, asks for confirmation]
       [applies upgrade or rolls back]

User: "How much space can I free up?"
Goose: [runs: python main.py optimize report]
       [interprets results]
       "You have 7 Xenia copies using ~15 GB. I recommend keeping only
        Xenia - 1.11k (latest). Also found 3 empty directories..."
```

### Hardware Requirements for Local Ollama + Goose
| Component | Minimum              | Recommended                             |
| --------- | -------------------- | --------------------------------------- |
| RAM       | 16 GB                | 32 GB                                   |
| GPU VRAM  | 6 GB (for 7B models) | 12+ GB (for 13B+ models)                |
| Storage   | 5 GB per model       | 20-50 GB for model library              |
| CPU       | Any modern x64       | Fast single-thread for quantized models |

---

## Tool 2: CLI-Anything (HKUDS) — Make Software Agent-Native

### What It Is
CLI-Anything is a framework that **automatically generates CLI wrappers for any software**, making it agent-controllable. It bridges the gap between AI agents that can reason and professional software that has no API.

### Key Capabilities
- **7-phase automated pipeline** — from codebase analysis to publishable CLI
- **Authentic software integration** — calls real applications, not toy reimplementations
- **Dual-mode operation** — REPL for interactive agent sessions + subcommands for scripting
- **`--json` flag on every command** — structured output for machine consumption
- **SKILL.md generation** — self-documenting for agent discovery
- **Production-grade testing** — unit + e2e + CLI subprocess verification
- **Zero-config install** — `pip install -e .` puts CLI on PATH

### Why It Helps Our Toolkit

**Use Case 1: Wrap HyperSpin itself**
HyperSpin has no API — it's a GUI-only application. CLI-Anything could generate a CLI wrapper that lets agents:
- Query which systems are configured
- Check theme/wheel/video assignments
- Modify settings programmatically

**Use Case 2: Wrap RocketLauncher**
RocketLauncher has XML configs and a GUI. A generated CLI could:
- List configured systems and their emulators
- Switch emulator assignments per system
- Test launches from command line

**Use Case 3: Wrap ClrMamePro / RomVault**
These ROM managers have GUIs. CLI-Anything could:
- Run ROM audits from the command line
- Generate fix DATs programmatically
- Rebuild ROM sets without GUI interaction

**Use Case 4: Make our own toolkit agent-native**
Run CLI-Anything against our toolkit codebase to auto-generate a polished, agent-optimized CLI with SKILL.md.

### Installation
```bash
# Prerequisites: Python 3.10+
git clone https://github.com/HKUDS/CLI-Anything.git
cd CLI-Anything

# For use with our own agent (not Claude Code specific):
pip install -e cli-anything-plugin/
```

### Generating a CLI for Our Toolkit
```bash
# Point CLI-Anything at our toolkit codebase
/cli-anything D:\hyperspin_toolkit

# This will:
# 1. Analyze our codebase
# 2. Design CLI architecture
# 3. Implement Click-based CLI
# 4. Generate tests
# 5. Create SKILL.md for agent discovery
# 6. Package for pip install
```

### Generated SKILL.md Example
```markdown
---
name: cli-anything-hyperspin
description: Agent-native CLI for HyperSpin Extreme Toolkit
---
# Commands
- `hyperspin audit full` — Run full ecosystem audit
- `hyperspin releases check` — Check all emulators for updates
- `hyperspin optimize report` — Space optimization analysis
- `hyperspin backup create <path>` — Create versioned backup
- `hyperspin ai ask "<question>"` — Query AI assistant
```

### Integration Architecture
```
User (natural language)
    ↓
Goose Agent (Ollama local LLM)
    ↓ reads SKILL.md
CLI-Anything generated CLI
    ↓ calls
HyperSpin Extreme Toolkit (our Python code)
    ↓ manages
D:\Arcade\ ecosystem (ROMs, emulators, media)
```

---

## Tool 3: NVIDIA OpenShell — Sandboxed Agent Runtime

### What It Is
OpenShell is a **safe, private runtime for autonomous AI agents**. It isolates each agent in a policy-controlled Docker container with:
- **Network policy enforcement** — controls which URLs agents can access
- **Filesystem isolation** — agents only see allowed paths
- **Inference routing** — manages how agents call LLMs
- **GPU passthrough** — for local inference in sandbox
- **Terminal UI** — real-time monitoring dashboard

### Why It's Medium Priority
**Pros:**
- Safety guarantees for autonomous operations (important when agents modify ROMs/emulators)
- Policy enforcement prevents agents from accessing unauthorized network resources
- Container isolation protects host system
- GPU support for local Ollama inference inside sandbox

**Cons:**
- Requires Docker Desktop + K3s (Kubernetes) — heavy dependency
- Alpha software — "Expect rough edges"
- Primarily designed for cloud inference, not local-first
- Overhead may be unnecessary for our use case since our toolkit already has snapshot/rollback safety

### When to Use OpenShell
- If you want to let agents **autonomously modify files** on your 12 TB arcade collection
- If you want strict **network isolation** (agent can only reach GitHub API, not random sites)
- If you plan to run **untrusted community agents** against your collection

### Installation
```powershell
# Prerequisites: Docker Desktop must be running
# Install via pip (requires uv):
pip install openshell

# Or binary install:
# Download from: https://github.com/NVIDIA/OpenShell/releases/tag/v0.0.8
```

### Example: Sandbox Our Toolkit Agent
```bash
# Create a sandbox with Ollama access
openshell sandbox create --gpu -- python

# Inside sandbox, install and run our toolkit
pip install -r requirements.txt
python main.py audit full

# Network policy: only allow GitHub API + Ollama
# policy.yaml:
# network:
#   egress:
#     - host: api.github.com
#       methods: [GET]
#     - host: localhost:11434
#       methods: [GET, POST]
```

---

## Tool 4: NVIDIA NemoClaw — OpenClaw Plugin

### What It Is
NemoClaw is a **plugin for OpenShell** that sets up NVIDIA's OpenClaw agent in a sandboxed environment. It routes inference through **NVIDIA cloud** (build.nvidia.com).

### Why It's Low Priority for Us
- **Routes inference to NVIDIA cloud** — we want LOCAL inference via Ollama/LM Studio
- **Requires NVIDIA API key** — adds cloud dependency we're trying to avoid
- **Alpha software** — interfaces may change without notice
- **Specific to OpenClaw agent** — doesn't help our custom agents

### When It Could Be Useful
- If you want to test NVIDIA's Nemotron models (very capable) for complex reasoning tasks
- If you get an NVIDIA developer API key and want cloud fallback when local models struggle
- Future: if NemoClaw adds Ollama/local provider support

### Installation (if needed later)
```bash
pip install nemoclaw
nemoclaw onboard  # will prompt for NVIDIA API key
```

---

## Recommended Integration Plan

### Phase 1: Goose + Ollama (Immediate — Highest Impact)

```
Install:
1. Install Goose v1.27.2 from GitHub releases
2. Configure Ollama as provider (llama3.1:8b or deepseek-coder-v2:16b)
3. Create MCP bridge for our toolkit

Result: Users can manage their entire HyperSpin collection via
        natural language conversation with a local AI agent
```

### Phase 2: CLI-Anything Wrapping (Week 2)

```
Actions:
1. Run CLI-Anything against our toolkit to generate agent-optimized CLI
2. Generate SKILL.md for Goose to discover our commands
3. Optionally wrap RocketLauncher and ClrMamePro

Result: Our toolkit becomes fully agent-native with structured
        JSON output on every command
```

### Phase 3: OpenShell Safety Layer (Month 2 — Optional)

```
Actions:
1. Install Docker Desktop if not present
2. Set up OpenShell sandbox for autonomous operations
3. Create network policies for safe agent operation
4. Run our toolkit agents inside sandboxed environment

Result: Maximum safety for autonomous file operations on
        the 12 TB arcade collection
```

---

## MCP Bridge Implementation

This is the key integration piece — exposing our toolkit as MCP tools for Goose:

```python
# D:\hyperspin_toolkit\mcp_bridge.py
"""MCP Bridge — exposes toolkit as Model Context Protocol tools for Goose."""

import json
import sys
from typing import Any

# MCP tool definitions that Goose can discover and call
TOOLS = {
    "audit_full": {
        "description": "Run a full HyperSpin ecosystem audit",
        "parameters": {},
        "handler": "engines.auditor:run_full_audit",
    },
    "check_updates": {
        "description": "Check all emulators for available updates via GitHub",
        "parameters": {},
        "handler": "engines.release_checker:check_all_emulators",
    },
    "optimize_report": {
        "description": "Analyze disk space and find optimization opportunities",
        "parameters": {},
        "handler": "engines.space_optimizer:full_optimization_report",
    },
    "backup_create": {
        "description": "Create a versioned backup of a directory",
        "parameters": {"source": "string", "label": "string"},
        "handler": "engines.backup:create_backup",
    },
    "discover_tools": {
        "description": "Check which external tools (MAME, Igir, etc.) are installed",
        "parameters": {},
        "handler": "engines.external_tools:discover_tools",
    },
    "find_duplicates": {
        "description": "Find duplicate ROM files across the collection",
        "parameters": {"directory": "string"},
        "handler": "engines.space_optimizer:find_duplicate_roms",
    },
    "ai_ask": {
        "description": "Ask the local AI assistant a question about the collection",
        "parameters": {"question": "string"},
        "handler": "engines.ai_engine:get_ai().ask",
    },
}
```

---

## Full Agentic Architecture

```
┌────────────────────────────────────────────────────────┐
│                    USER (Natural Language)              │
│  "Check my emulators for updates and free up space"    │
└───────────────────────┬────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────┐
│              Goose Agent (v1.27.2)                      │
│  Provider: Ollama (llama3.1:8b / deepseek-coder-v2)   │
│  Extensions: MCP tools, file system, web               │
└───────────────────────┬────────────────────────────────┘
                        │ MCP Protocol
┌───────────────────────▼────────────────────────────────┐
│           CLI-Anything Generated CLI                    │
│  SKILL.md auto-discovered │ --json structured output   │
│  REPL mode for sessions   │ Subcommands for scripts    │
└───────────────────────┬────────────────────────────────┘
                        │ Python calls
┌───────────────────────▼────────────────────────────────┐
│          HyperSpin Extreme Toolkit                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Auditor  │ │ Backup   │ │ Updater  │ │ Optimizer│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Scanner  │ │ AI Engine│ │ Releases │ │ Ext Tools│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
└───────────────────────┬────────────────────────────────┘
                        │ File system operations
┌───────────────────────▼────────────────────────────────┐
│     D:\Arcade\ (12 TB HyperSpin Ecosystem)             │
│  184 systems │ 173 emulators │ 421 media │ ROMs        │
└────────────────────────────────────────────────────────┘

Optional Safety Layer:
┌────────────────────────────────────────────────────────┐
│     NVIDIA OpenShell (Docker sandbox)                   │
│  Network policy │ Filesystem isolation │ GPU passthrough│
└────────────────────────────────────────────────────────┘
```

---

## Quick Start: Get Agentic in 30 Minutes

### Step 1: Ensure Ollama is running with a model
```bash
ollama pull llama3.1:8b
ollama serve  # if not already running
```

### Step 2: Install Goose
```powershell
# Download Windows installer from:
# https://github.com/block/goose/releases/tag/v1.27.2
# Run the installer
```

### Step 3: Configure Goose for Ollama
```bash
goose configure
# Provider: ollama
# Model: llama3.1:8b
```

### Step 4: Test with our toolkit
```bash
goose session start
> Can you run a full audit of my HyperSpin collection?
> Check which emulators need updates
> How much disk space can I recover?
```

### Step 5 (Optional): Generate agent-native CLI
```bash
git clone https://github.com/HKUDS/CLI-Anything.git
# Follow CLI-Anything setup for your agent platform
# Point at D:\hyperspin_toolkit to generate optimized CLI
```

---

## Summary

| Tool             | Role            | Local LLM Support | Install Effort    | Impact       |
| ---------------- | --------------- | ----------------- | ----------------- | ------------ |
| **Goose**        | Agent runtime   | Ollama, LM Studio | Easy (installer)  | **CRITICAL** |
| **CLI-Anything** | CLI generator   | Agent-agnostic    | Medium (Python)   | **HIGH**     |
| **OpenShell**    | Safety sandbox  | GPU passthrough   | Hard (Docker+K3s) | **MEDIUM**   |
| **NemoClaw**     | OpenClaw plugin | Cloud only        | Medium            | **LOW**      |

**Bottom line**: Goose + Ollama gives you an immediately usable, fully local AI agent that can manage your entire HyperSpin ecosystem through our toolkit. CLI-Anything makes it even smoother by auto-generating agent-optimized interfaces. OpenShell adds safety for fully autonomous operations. NemoClaw is not needed for local-first operation.
