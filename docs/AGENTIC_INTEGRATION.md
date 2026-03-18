# Agentic AI Integration Plan — HyperSpin Toolkit

> **Last Updated:** 2026-03-17  
> **Status:** Research & Architecture Phase

---

## Overview

The HyperSpin Toolkit evolves from a CLI/dashboard tool into a **fully agentic platform** where autonomous AI agents manage, audit, optimize, and interact with game collections across all HDDs. The architecture combines:

- **Goose** — Local AI agent orchestrator (MCP-native, any LLM)
- **OpenHands** — AI-driven development platform (Docker sandbox, coding agent)
- **NemoClaw** — NVIDIA agent sandbox orchestration (secure agent lifecycle)
- **OpenShell** — NVIDIA secure sandbox runtime (kernel-level isolation)
- **CLI-Anything** — Makes any software agent-native via generated CLIs + Skills
- **VLLM** — High-throughput LLM inference server (optional performance backend)
- **LM Studio** — Default local LLM backend (`C:\Users\Admin\.lmstudio\models`)
- **Ollama** — Secondary local LLM backend (`C:\Users\Admin\.ollama\models`)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER / ARCADE GUI (C#/WPF)                   │
│         SOTA Arcade Interface with Game Asset Visuals           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket / REST API
┌──────────────────────────▼──────────────────────────────────────┐
│              ORCHESTRATION LAYER                                 │
│                                                                  │
│   ┌─────────────┐    ┌──────────────┐    ┌───────────────────┐  │
│   │   GOOSE     │◄──►│  OPENHANDS   │◄──►│   MCP BRIDGE      │  │
│   │  (Agent     │    │  (Coding     │    │  (HyperSpin       │  │
│   │   Control)  │    │   Agent)     │    │   Toolkit API)    │  │
│   └──────┬──────┘    └──────┬───────┘    └───────────────────┘  │
│          │                  │                                    │
│          ▼                  ▼                                    │
│   ┌─────────────────────────────────────────┐                   │
│   │         SKILL REGISTRY                   │                   │
│   │  CLI-Anything generated Skills           │                   │
│   │  HyperSpin SKILL.md                      │                   │
│   │  Drive Management SKILL.md               │                   │
│   │  Asset Audit SKILL.md                    │                   │
│   │  Emulator Config SKILL.md                │                   │
│   └─────────────────────────────────────────┘                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              SANDBOX LAYER (NVIDIA)                               │
│                                                                  │
│   ┌──────────────┐    ┌──────────────────────────────────────┐  │
│   │  NEMOCLAW     │    │  OPENSHELL SANDBOXES                 │  │
│   │  (Agent       │───►│                                      │  │
│   │   Lifecycle)  │    │  ┌────────────┐  ┌────────────┐     │  │
│   └──────────────┘    │  │ Agent: ROM  │  │ Agent:     │     │  │
│                        │  │ Auditor    │  │ Emulator   │     │  │
│                        │  │            │  │ Health     │     │  │
│                        │  └────────────┘  └────────────┘     │  │
│                        │  ┌────────────┐  ┌────────────┐     │  │
│                        │  │ Agent:     │  │ Agent:     │     │  │
│                        │  │ Asset      │  │ Backup     │     │  │
│                        │  │ Scanner    │  │ Manager    │     │  │
│                        │  └────────────┘  └────────────┘     │  │
│                        └──────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              LLM INFERENCE LAYER                                 │
│                                                                  │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│   │  LM STUDIO   │  │   OLLAMA     │  │    VLLM      │         │
│   │  (Default)   │  │  (Secondary) │  │  (Perf Mode) │         │
│   │  Port 1234   │  │  Port 11434  │  │  Port 8000   │         │
│   │              │  │              │  │              │         │
│   │  Models at:  │  │  Models at:  │  │  OpenAI-     │         │
│   │  C:\Users\   │  │  C:\Users\   │  │  compatible  │         │
│   │  Admin\      │  │  Admin\      │  │  API         │         │
│   │  .lmstudio\  │  │  .ollama\    │  │              │         │
│   │  models      │  │  models      │  │              │         │
│   └──────────────┘  └──────────────┘  └──────────────┘         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│              DATA LAYER (Gaming HDDs)                             │
│                                                                  │
│  D: TEST_HYPERSPIN    I: PRIMARY_HYPERSPIN   K: ATTRACTION      │
│  L: CORE_TYPE_R       H: BACKUP_14TB         J: ROM_BACKUP      │
│  E: ARCHIVE           M:+N: BATOCERA                            │
│                                                                  │
│  301K PNGs │ 47K Videos │ 20K Audio │ 8K SWF Themes             │
│  184+ Systems (HyperSpin) │ 219 Systems (Batocera)              │
│  199 Collections (Attract Mode) │ CORE-TYPE R Assets            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Roles & Responsibilities

### 1. Goose (Block/goose) — Primary Orchestrator

**Role:** Top-level AI agent that coordinates all other agents and tools.

| Feature            | Use in Project                                        |
| ------------------ | ----------------------------------------------------- |
| MCP-native         | Direct integration with HyperSpin Toolkit MCP Bridge  |
| Any LLM support    | Routes to LM Studio (default), Ollama, or VLLM        |
| Multi-model config | Use small model for routing, large model for analysis |
| Desktop + CLI      | Both GUI and headless operation modes                 |
| Extension system   | Custom extensions for drive management, ROM audit     |
| Skill discovery    | Reads SKILL.md files from CLI-Anything generated CLIs |

**Integration Points:**
- Connects to `mcp_bridge.py` as an MCP server
- Controls NemoClaw agent lifecycle (create/destroy/monitor)
- Delegates coding tasks to OpenHands
- Uses CLI-Anything Skills for HyperSpin, emulator, and tool control

**Setup:**
```powershell
# Install Goose
winget install Block.Goose
# Or download from https://github.com/block/goose/releases/tag/v1.27.2

# Configure LM Studio as default provider
goose configure --provider lmstudio --base-url http://localhost:1234/v1

# Add HyperSpin Toolkit as MCP server
goose mcp add hyperspin-toolkit -- python D:\hyperspin_toolkit\mcp_bridge.py
```

### 2. OpenHands — Coding & Development Agent

**Role:** Autonomous coding agent that writes, tests, and fixes code inside Docker sandboxes.

| Feature           | Use in Project                                        |
| ----------------- | ----------------------------------------------------- |
| Docker sandbox    | Safe code execution environment                       |
| File editing      | Autonomous code changes to toolkit engines            |
| Terminal access   | Run pytest, build commands, PowerShell scripts        |
| Web browsing      | Research emulator updates, ROM databases              |
| Local LLM support | Works with LM Studio/Ollama via OpenAI-compatible API |
| Multi-agent       | Can spawn sub-agents for parallel tasks               |

**Integration Points:**
- Goose delegates coding tasks to OpenHands
- OpenHands edits `engines/*.py`, `tests/*.py`, `dashboard/app.py`
- Runs test suites inside sandbox
- Generates new CLI-Anything Skills for newly discovered software

**Setup:**
```powershell
# Pull OpenHands Docker image
docker pull ghcr.io/openhands/openhands:latest

# Run with LM Studio backend
docker run -it --rm `
  -e LLM_BASE_URL="http://host.docker.internal:1234/v1" `
  -e LLM_API_KEY="lm-studio" `
  -e LLM_MODEL="local-model" `
  -v D:\hyperspin_toolkit:/workspace `
  -p 3000:3000 `
  ghcr.io/openhands/openhands:latest
```

### 3. NemoClaw (NVIDIA) — Agent Sandbox Orchestration

**Role:** Manages the lifecycle of specialized AI agents running in OpenShell sandboxes.

| Feature            | Use in Project                                 |
| ------------------ | ---------------------------------------------- |
| Blueprint system   | Versioned, immutable agent configurations      |
| Sandbox creation   | Isolated containers per agent task             |
| Policy enforcement | Filesystem, network, GPU access control        |
| Inference routing  | Routes LLM calls through configured providers  |
| CLI plugin         | `nemoclaw onboard`, `nemoclaw status` commands |

**Integration Points:**
- Goose/OpenHands create NemoClaw blueprints for specialized agents
- Each agent type gets its own sandbox policy:
  - **ROM Auditor Agent** — read-only access to all gaming drives
  - **Emulator Health Agent** — read-only drives + write to test drive D:
  - **Asset Scanner Agent** — read-only drives + write to toolkit output
  - **Backup Manager Agent** — read-write to H: backup target only
- NemoClaw manages agent start/stop/restart lifecycle

**Setup:**
```powershell
# Install NemoClaw
git clone https://github.com/NVIDIA/NemoClaw.git C:\tools\NemoClaw
cd C:\tools\NemoClaw
npm install

# Configure with local inference (override NVIDIA cloud default)
nemoclaw configure --inference-provider lmstudio --base-url http://localhost:1234/v1

# Onboard the HyperSpin toolkit blueprint
nemoclaw onboard --blueprint D:\hyperspin_toolkit\blueprints\hyperspin-agent.yaml
```

### 4. OpenShell (NVIDIA) — Secure Sandbox Runtime

**Role:** Kernel-level isolation for running untrusted agent code safely.

| Feature             | Use in Project                            |
| ------------------- | ----------------------------------------- |
| Container isolation | Agents can't escape sandbox               |
| Filesystem policies | Per-drive read/write/deny rules           |
| Network policies    | Only allow required endpoints             |
| GPU passthrough     | Local inference inside sandbox            |
| CLI management      | `openshell sandbox create/destroy/status` |

**See:** `docs/OPENSHELL_SETUP.md` for full setup and policy configuration.

### 5. CLI-Anything (HKUDS) — Software-to-Agent Bridge

**Role:** Generates deterministic CLIs + SKILL.md files that make any software agent-controllable.

| Feature             | Use in Project                                  |
| ------------------- | ----------------------------------------------- |
| Auto-generated CLIs | Wrap HyperSpin, RocketLauncher, MAME, RetroArch |
| SKILL.md generation | Agents auto-discover available capabilities     |
| 7-phase pipeline    | Analyze → Design → Implement → Test → Document  |
| Zero-config install | `pip install cli-anything-<software>`           |
| Session management  | Stateful interactions with complex software     |

**Already on D:\CLI-Anything** — includes generated CLIs for: audacity, blender, comfyui, drawio, gimp, inkscape, kdenlive, libreoffice, mermaid, obs-studio, and more.

**New CLIs to Generate for This Project:**
```
cli-anything-hyperspin      # Control HyperSpin frontend
cli-anything-rocketlauncher # Control RocketLauncher backend
cli-anything-mame           # Control MAME emulator
cli-anything-retroarch      # Control RetroArch core system
cli-anything-batocera        # Control Batocera OS
cli-anything-launchbox      # Control LaunchBox/BigBox (for CORE-TYPE R)
cli-anything-lmstudio       # Control LM Studio inference
cli-anything-ollama         # Control Ollama inference
```

**Integration:**
```powershell
# Generate HyperSpin CLI from source
cd D:\CLI-Anything
# Use the plugin to generate
/cli-anything:generate D:\Arcade\HyperSpin.exe

# Each generated CLI includes SKILL.md for agent discovery
# Goose auto-loads Skills: goose skill load cli-anything-hyperspin
```

### 6. VLLM — High-Performance Inference

**Role:** Optional high-throughput LLM server for batch operations and multi-agent concurrent inference.

| Feature               | Use in Project                           |
| --------------------- | ---------------------------------------- |
| PagedAttention        | 3x throughput vs Ollama                  |
| OpenAI-compatible API | Drop-in replacement for LM Studio        |
| Batch processing      | Efficient for bulk ROM metadata analysis |
| Multi-GPU support     | Scale across available GPUs              |
| Continuous batching   | Handle concurrent agent requests         |

**When to Use VLLM vs LM Studio:**
| Scenario                                 | Backend                                |
| ---------------------------------------- | -------------------------------------- |
| Interactive chat/development             | LM Studio (GUI, easy model switching)  |
| Single agent tasks                       | LM Studio or Ollama                    |
| Multi-agent concurrent inference         | **VLLM** (handles concurrent requests) |
| Batch ROM metadata analysis (47K+ items) | **VLLM** (continuous batching)         |
| Asset classification at scale            | **VLLM** (throughput)                  |
| Quick prototyping                        | Ollama (CLI, fast model pull)          |

**Setup:**
```powershell
# Install VLLM (requires CUDA)
pip install vllm

# Start server with a local model
python -m vllm.entrypoints.openai.api_server `
  --model "C:\Users\Admin\.lmstudio\models\<model-path>" `
  --port 8000 `
  --gpu-memory-utilization 0.85
```

---

## Orchestration Flow

### How Goose + OpenHands Control NemoClaw Agents

```
User Request: "Audit all ROM collections and find missing media"
    │
    ▼
┌─────────────────────────────────────────────────┐
│ GOOSE (Orchestrator)                             │
│                                                  │
│ 1. Parse user intent → "ROM audit + media scan"  │
│ 2. Load Skills: cli-anything-hyperspin,          │
│    drive-management, asset-audit                 │
│ 3. Plan multi-agent workflow:                    │
│    a) ROM Auditor → scan D:, I:, K:, L:, N:     │
│    b) Asset Scanner → scan Media/ directories    │
│    c) Report Generator → compile results         │
│ 4. Delegate to NemoClaw for sandbox execution    │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ NEMOCLAW (Agent Lifecycle)                       │
│                                                  │
│ Create sandboxes with drive_registry.json        │
│ policies:                                        │
│                                                  │
│ Sandbox 1: ROM Auditor Agent                     │
│   - Read: D:\Arcade, I:\Arcade, K:\Arcade,      │
│     L:\CORE - TYPE R, N:\roms                    │
│   - Write: D:\HyperSpin_Toolkit_Output\audit     │
│   - LLM: LM Studio (for metadata classification)│
│                                                  │
│ Sandbox 2: Asset Scanner Agent                   │
│   - Read: D:\Arcade\Media, K:\Arcade\menu-art,  │
│     L:\CORE - TYPE R\collections\Main            │
│   - Write: D:\HyperSpin_Toolkit_Output\assets    │
│   - LLM: VLLM (batch image classification)       │
│                                                  │
│ Sandbox 3: Report Generator Agent                │
│   - Read: Output from Sandbox 1 & 2             │
│   - Write: D:\HyperSpin_Toolkit_Output\reports   │
│   - LLM: LM Studio (report generation)          │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ OPENSHELL (Sandbox Runtime)                      │
│                                                  │
│ Each sandbox runs isolated with:                 │
│ - Filesystem policies from drive_registry.json   │
│ - GPU access for local inference                 │
│ - Network restricted to localhost LLM only       │
│ - Resource limits (RAM, CPU, timeout)            │
│                                                  │
│ Agents execute tasks, return results to Goose    │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│ GOOSE (Results Aggregation)                      │
│                                                  │
│ 5. Collect results from all agents               │
│ 6. If code changes needed → delegate to OpenHands│
│ 7. If fixes needed → create action items         │
│ 8. Present results to user via Arcade GUI        │
│ 9. Store results in toolkit database             │
└─────────────────────────────────────────────────┘
```

### Seamless Collaboration Pattern

| Step | Actor         | Action                                                   |
| ---- | ------------- | -------------------------------------------------------- |
| 1    | **User**      | Requests task via Arcade GUI or CLI                      |
| 2    | **Goose**     | Interprets intent, loads relevant Skills                 |
| 3    | **Goose**     | Creates execution plan, identifies required agents       |
| 4    | **NemoClaw**  | Provisions OpenShell sandboxes per agent                 |
| 5    | **Agents**    | Execute tasks in isolation (ROM scan, asset audit, etc.) |
| 6    | **Agents**    | Query LM Studio/Ollama/VLLM for AI-powered analysis      |
| 7    | **NemoClaw**  | Monitors agent health, restarts on failure               |
| 8    | **Goose**     | Aggregates results, detects code changes needed          |
| 9    | **OpenHands** | Implements code changes (new engines, bug fixes, tests)  |
| 10   | **Goose**     | Validates changes, reports to user via GUI               |

---

## Skill Registry

Skills are the **discovery mechanism** that lets agents know what capabilities are available. Each Skill is a `SKILL.md` file that describes inputs, outputs, and usage.

### Required Skills for HyperSpin Toolkit

| Skill                       | Source                 | Purpose                              |
| --------------------------- | ---------------------- | ------------------------------------ |
| `hyperspin-management`      | CLI-Anything generated | Control HyperSpin frontend           |
| `rocketlauncher-management` | CLI-Anything generated | Control RocketLauncher backend       |
| `mame-control`              | CLI-Anything generated | Control MAME emulator                |
| `retroarch-control`         | CLI-Anything generated | Control RetroArch cores              |
| `drive-management`          | Custom SKILL.md        | Drive registry, health, backup ops   |
| `rom-audit`                 | Custom SKILL.md        | ROM scanning, validation, dedup      |
| `asset-audit`               | Custom SKILL.md        | Media asset scanning, classification |
| `emulator-health`           | Custom SKILL.md        | Emulator version tracking, updates   |
| `collection-sync`           | Custom SKILL.md        | Cross-drive sync operations          |
| `arcade-gui-assets`         | Custom SKILL.md        | Asset selection for GUI theming      |
| `backup-management`         | Custom SKILL.md        | Clone, verify, schedule backups      |
| `lm-studio-control`         | CLI-Anything generated | Model loading, inference config      |
| `ollama-control`            | CLI-Anything generated | Model pull, run, manage              |

### Skill File Format

```markdown
# SKILL: drive-management

## Description
Manage gaming HDD inventory, health monitoring, and backup operations
using the drive_registry.json for persistent drive identification.

## Commands
- `drive list` — List all registered drives with health status
- `drive identify <serial>` — Look up drive by serial number
- `drive health <letter>` — Get detailed health report for a drive
- `drive backup <source> <target>` — Initiate backup/clone operation
- `drive scan <letter>` — Scan drive contents and update manifest

## Input
- Drive letter, serial number, or tag from drive_registry.json

## Output
- JSON-formatted drive information, health data, or operation status

## Dependencies
- engines/drive_indexer.py
- drive_registry.json
```

---

## LLM Backend Configuration

### Provider Priority (Fallback Chain)

```
1. LM Studio (default)  → http://localhost:1234/v1
2. Ollama (fallback)     → http://localhost:11434/v1
3. VLLM (batch/perf)     → http://localhost:8000/v1
```

### Configuration File: `llm_config.yaml`

```yaml
providers:
  default:
    name: lmstudio
    base_url: http://localhost:1234/v1
    api_key: lm-studio
    models:
      chat: auto  # Use whatever model is loaded in LM Studio
      embedding: auto
    
  fallback:
    name: ollama
    base_url: http://localhost:11434/v1
    api_key: ollama
    models:
      chat: llama3.1:8b
      embedding: nomic-embed-text
    
  performance:
    name: vllm
    base_url: http://localhost:8000/v1
    api_key: vllm
    models:
      chat: auto
    use_when:
      - concurrent_agents > 2
      - batch_size > 100
      - task_type: "bulk_classification"

routing:
  # Automatic provider selection based on task
  interactive: default
  coding: default
  batch_analysis: performance
  multi_agent: performance
  quick_query: fallback
```

---

## Implementation Phases

### Phase A: Foundation (Weeks 1-2)
- [ ] Install Goose v1.27.2 and configure with LM Studio
- [ ] Install OpenHands Docker image
- [ ] Install NemoClaw and OpenShell v0.0.8
- [ ] Configure CLI-Anything for HyperSpin/RocketLauncher/MAME
- [ ] Create `llm_config.yaml` with provider priority chain
- [ ] Create custom SKILL.md files for drive-management and rom-audit

### Phase B: Skill Generation (Weeks 2-3)
- [ ] Generate `cli-anything-hyperspin` from HyperSpin.exe
- [ ] Generate `cli-anything-rocketlauncher` from RocketLauncher
- [ ] Generate `cli-anything-mame` from MAME executable
- [ ] Generate `cli-anything-retroarch` from RetroArch
- [ ] Generate `cli-anything-lmstudio` from LM Studio
- [ ] Generate `cli-anything-ollama` from Ollama CLI
- [ ] Test all generated CLIs and verify SKILL.md accuracy

### Phase C: Agent Blueprints (Weeks 3-4)
- [ ] Create NemoClaw blueprint: ROM Auditor Agent
- [ ] Create NemoClaw blueprint: Asset Scanner Agent
- [ ] Create NemoClaw blueprint: Emulator Health Agent
- [ ] Create NemoClaw blueprint: Backup Manager Agent
- [ ] Define OpenShell policies per agent type using drive_registry.json
- [ ] Test sandbox creation and agent execution

### Phase D: Orchestration (Weeks 4-6)
- [ ] Configure Goose MCP connection to HyperSpin Toolkit
- [ ] Build orchestration workflows (YAML-based)
- [ ] Implement Goose ↔ NemoClaw ↔ OpenHands communication
- [ ] Test multi-agent workflows end-to-end
- [ ] Implement automatic LLM backend selection (LM Studio → VLLM fallback)

### Phase E: Arcade GUI Integration (Weeks 6-8)
- [ ] Build C#/WPF Arcade GUI (see ARCADE_GUI_PLAN.md)
- [ ] Connect GUI to Goose orchestrator via WebSocket
- [ ] Implement agent status visualization in GUI
- [ ] Add asset-driven theming using scanned media
- [ ] End-to-end testing of full agentic pipeline

---

## Security Model

| Layer              | Control                | Policy                                  |
| ------------------ | ---------------------- | --------------------------------------- |
| **OpenShell**      | Kernel-level isolation | Per-agent filesystem/network/GPU rules  |
| **NemoClaw**       | Agent lifecycle        | Blueprint-enforced boundaries           |
| **Drive Registry** | Drive identification   | Serial-based verification before writes |
| **Goose**          | Task routing           | Only delegates to authorized agents     |
| **OpenHands**      | Code sandbox           | Docker isolation, no host access        |
| **LLM**            | Inference routing      | Localhost-only, no cloud calls          |

### Critical Safety Rules
1. **NEVER** allow write access to I:, K:, L:, J: from any agent
2. **ONLY** D: (testing drive) gets write access for agents
3. All agent writes go to `D:\HyperSpin_Toolkit_Output\` by default
4. Drive serial verification (`drive_registry.json`) before any disk operation
5. All inference stays local (LM Studio / Ollama / VLLM) — no cloud APIs
