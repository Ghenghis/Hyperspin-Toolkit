# HyperSpin Extreme Toolkit — Agentic Stack Architecture

> **Zero cloud. All local. RTX 3090 Ti (24 GB VRAM). Fully autonomous.**

---

## Stack Overview

```
╔══════════════════════════════════════════════════════════════════════════╗
║                        USER (natural language)                           ║
╚══════════════════════════════════╦═══════════════════════════════════════╝
                                   ║
                    ┌──────────────▼──────────────┐
                    │         G O O S E           │
                    │      (Orchestrator AI)       │
                    │                              │
                    │  Provider: LM Studio         │
                    │  Model: Devstral-24B Q4_K_M  │
                    │  Context: 131,072 tokens     │
                    │  Skills: 11 × SKILL.md       │
                    │  Mode: smart_approve         │
                    └──┬─────────┬────────┬────────┘
                       │         │        │        │
          ┌────────────▼─┐ ┌─────▼──┐ ┌──▼───┐ ┌──▼──────────┐
          │  HyperSpin   │ │  CLI-  │ │Nemo- │ │  OpenHands  │
          │ Toolkit MCP  │ │Anything│ │ Claw │ │   Bridge    │
          │              │ │ Bridge │ │Agents│ │             │
          │ 236 MCP tools │ │NL→CLI  │ │6 rôles│ │ REST→:3000 │
          └──────┬───────┘ └────┬───┘ └──┬───┘ └──┬──────────┘
                 │              │         │         │
                 └──────────────┴─────────┴─────────┘
                                      │
                    ┌─────────────────▼──────────────────┐
                    │     D:\hyperspin_toolkit\           │
                    │        Python CLI Engine            │
                    │                                     │
                    │  main.py — 8 command groups         │
                    │  engines/ — 58 specialist modules   │
                    └─────────────────┬──────────────────┘
                                      │
                    ┌─────────────────▼──────────────────┐
                    │         D:\Arcade\  (12 TB)         │
                    │                                     │
                    │  ROMs/        ~60k+ ROMs            │
                    │  emulators/   173 emulators         │
                    │  HyperSpin/   421 media dirs        │
                    │  Databases/   422 XML files         │
                    │  RocketLaunch/ all modules          │
                    └────────────────────────────────────┘
```

---

## Component Detail

### 1. Goose — The Orchestrator

```
Configuration:  %APPDATA%\Block\goose\config\config.yaml
Provider:       LM Studio → http://localhost:1234/v1
Primary Model:  Devstral-Small-2-24B-Instruct Q4_K_M  (13.35 GB, 32K ctx)
Fallback Model: Qwen3.5-27B Opus 4.6 Distilled Q4_K_S (14.52 GB, 128K ctx)
Mode:           smart_approve (asks before destructive actions)
```

**What Goose does:**
- Receives user intent in plain English
- Loads the matching SKILL.md to understand domain context
- Decides which sub-system to call (Toolkit MCP / CLI-Anything / NemoClaw / OpenHands)
- Chains multiple calls together for complex goals
- Presents results and asks for confirmation before any destructive step

**Extensions active:**

| Extension Key        | Type      | What it provides                    |
| -------------------- | --------- | ----------------------------------- |
| `hyperspin_toolkit`  | stdio MCP | 70+ direct toolkit tools            |
| `cli_anything`       | stdio MCP | NL → CLI command translation        |
| `nemoclaw_agents`    | stdio MCP | 6 specialist reasoning agents       |
| `openhands_bridge`   | stdio MCP | Multi-file operations via OpenHands |
| `skills`             | platform  | Loads 11 × SKILL.md files           |
| `developer`          | builtin   | Shell + file system access          |
| `computercontroller` | builtin   | Desktop UI automation               |
| `memory`             | builtin   | Persistent user preferences         |
| `summon`             | platform  | Sub-agent delegation                |

---

### 2. HyperSpin Toolkit MCP Bridge (70+ tools)

```
Script:   D:\hyperspin_toolkit\mcp_bridge.py
Protocol: JSON-RPC 2.0 over stdio
Timeout:  600 seconds
```

| Tool                       | Description                            |
| -------------------------- | -------------------------------------- |
| `audit_full`               | Full ecosystem audit — all 184 systems |
| `audit_system`             | Single system audit by name            |
| `check_all_updates`        | Check 20+ emulators vs GitHub releases |
| `check_emulator_update`    | Check one emulator                     |
| `optimize_report`          | Full space optimization analysis       |
| `find_duplicates`          | Hash-based duplicate ROM finder        |
| `find_redundant_emulators` | Multiple-version emulator finder       |
| `find_large_files`         | Largest files by size threshold        |
| `discover_tools`           | Check MAME, Igir, Flips, 7z, etc.      |
| `backup_create`            | Versioned directory backup             |
| `get_stats`                | Collection statistics                  |
| `disk_usage`               | Drive usage summary                    |
| `mame_version`             | MAME version + path                    |
| `mame_listxml`             | Generate MAME -listxml XML database    |

---

### 3. CLI-Anything Bridge

```
Script:   D:\hyperspin_toolkit\engines\cli_anything_bridge.py
Protocol: JSON-RPC 2.0 over stdio
Timeout:  60 seconds
```

**Purpose:** Translate ambiguous natural language into exact `python main.py` commands.

```
"check my MAME" ──────────────────────────► audit system "MAME"
"free up space" ──────────────────────────► optimize report
"is dolphin up to date?" ─────────────────► releases check --emulator Dolphin
"snapshot before I change anything" ──────► backup create "<path>" --label "..."
```

**Resolution methods (in order):**
1. **Static map** (instant, confidence=1.0) — 30+ exact phrase patterns
2. **LM Studio LLM** (fast, confidence=0.85) — Devstral-24B reasoning
3. **Ollama fallback** (confidence=0.8) — if LM Studio not running
4. **Failure** (confidence=0.0) — shows help text

**MCP Tools:**
- `cli_resolve(task)` — translate only, return command + confidence
- `cli_run(task, auto_execute)` — translate + optionally execute

---

### 4. NemoClaw Agents (6 Specialist Roles)

```
Script:   D:\hyperspin_toolkit\engines\nemoclaw_agents.py
Protocol: JSON-RPC 2.0 over stdio
Timeout:  300 seconds
LLM:      LM Studio (primary) / Ollama (fallback) — NO NVIDIA CLOUD
```

Each agent has a deep system prompt tuned to its domain. Goose routes tasks by keyword matching, then invokes the agent which reasons with the local LLM and returns `ACTION:`, `WARNING:`, and `NEXT:` items.

| Agent                | Model            | Handles                                                  |
| -------------------- | ---------------- | -------------------------------------------------------- |
| `RomSpecialist`      | Devstral-24B     | ROM validation, hashing, MAME parent/clone relationships |
| `EmulatorSpecialist` | Devstral-24B     | Config, RocketLauncher modules, upgrade safety           |
| `MediaSpecialist`    | GLM-4.6V-Flash   | Artwork quality, coverage, scraping recommendations      |
| `DatabaseSpecialist` | Qwen3.5-9B Opus  | HyperSpin XML, game list sync, MAME listxml              |
| `SpaceOptimizer`     | Qwen3.5-9B Opus  | Disk analysis, duplicate detection, archive cleanup      |
| `UpdateOrchestrator` | Qwen3.5-27B Opus | Multi-emulator update sequencing, risk scoring           |

**MCP Tools:**
- `nemoclaw_delegate(task, context?, agent_name?)` — single agent call
- `nemoclaw_plan(goal, context?)` — multi-agent parallel planning
- `nemoclaw_list_agents()` — list all agents and roles

---

### 5. OpenHands Bridge

```
Script:   D:\hyperspin_toolkit\engines\openhands_bridge.py
Protocol: JSON-RPC 2.0 over stdio (proxies to HTTP REST)
Server:   http://localhost:3000  (Docker container)
Timeout:  600 seconds
```

**Purpose:** Delegate complex multi-file operations that are too large for a single MCP tool call.

Use OpenHands when the task requires:
- Editing hundreds of `.ini` files across all 173 emulators
- Generating filtered HyperSpin XML from a 500 MB MAME listxml file
- Browser automation (scraping EmuMovies, downloading updates)
- Writing and running custom Python scripts inline
- Multi-step shell sequences with live feedback

**MCP Tools:**
- `openhands_status()` — check if server is running
- `openhands_run_task(task, timeout?)` — free-form autonomous task
- `openhands_update_ini(system, key, value)` — single INI edit
- `openhands_batch_paths(old_path, new_path)` — update all INIs
- `openhands_analyse_roms(system, roms_path)` — ROM dir statistics

**Start OpenHands:**
```powershell
docker run -it -p 3000:3000 `
  -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest `
  docker.all-hands.dev/all-hands-ai/openhands:latest
```

---

## Data Flow Diagrams

### Flow A — Simple Query ("Show me collection stats")

```
User: "Show me collection stats"
  │
  ▼
Goose loads hyperspin-toolkit/SKILL.md
  │
  ▼
Toolkit MCP: get_stats()
  │
  ▼
Returns: { systems:184, total_roms:60247, emulators:173, ... }
  │
  ▼
Goose formats and displays table to user
```

---

### Flow B — Specialist Reasoning ("Fix my MAME setup")

```
User: "Fix my MAME setup"
  │
  ▼
Goose loads hyperspin-mame/SKILL.md
  │
  ├─► Toolkit MCP: mame_version()
  │     → { version:"0.228", path:"D:\Arcade\emulators\MAME\mame64.exe" }
  │
  ├─► Toolkit MCP: audit_system("MAME")
  │     → { health_score:42, missing_roms:1847, xml_games:8205, ... }
  │
  ├─► NemoClaw: nemoclaw_delegate(
  │     task="MAME health=42%, 1847 missing ROMs, version 0.228. What to fix?",
  │     context="<audit JSON>",
  │     agent_name="EmulatorSpecialist"
  │   )
  │     → ACTION: Run mame -listxml to regenerate database
  │       ACTION: Update MAME from 0.228 to 0.273
  │       WARNING: 45 version gap — test each version step
  │       NEXT: Verify ROM directory paths in RocketLauncher
  │
  ├─► CLI-Anything: cli_resolve("check MAME update")
  │     → "python main.py releases check --emulator MAME"
  │
  └─► Goose presents prioritised action plan to user
        "MAME needs: 1) Update to 0.273  2) Regenerate XML  3) Fix ROM paths"
```

---

### Flow C — Batch File Operation ("Update all RocketLauncher paths for MAME")

```
User: "I moved MAME to D:\Arcade\emulators\MAME_0273 — update everything"
  │
  ▼
Goose loads hyperspin-orchestrator/SKILL.md
  │
  ├─► Toolkit MCP: backup_create(
  │     source="D:\Arcade\RocketLauncher\Settings",
  │     label="pre-mame-path-update"
  │   )
  │
  ├─► OpenHands: openhands_batch_paths(
  │     old_path="D:\Arcade\emulators\MAME",
  │     new_path="D:\Arcade\emulators\MAME_0273"
  │   )
  │     → OpenHands server searches all .ini files
  │       Updates every occurrence
  │       Reports: 47 files changed, 312 lines updated
  │
  └─► Toolkit MCP: audit_system("MAME")
        → health_score improved: 42% → 78%
```

---

### Flow D — Multi-Agent Planning ("Clean up 100 GB and update everything")

```
User: "I want to free up 100GB and update all emulators safely"
  │
  ▼
Goose loads hyperspin-orchestrator/SKILL.md
  │
  ├─► NemoClaw: nemoclaw_plan(goal="free 100GB + update all emulators")
  │     → SpaceOptimizer: duplicate ROMs = 67 GB, redundant emus = 18 GB
  │       UpdateOrchestrator: MAME (HIGH), PCSX2 (MEDIUM), RetroArch (LOW)
  │       EmulatorSpecialist: backup all before touching anything
  │
  ├─► Toolkit MCP: optimize_report()      → confirms 85 GB recoverable
  ├─► Toolkit MCP: check_all_updates()    → 8 emulators need updates
  ├─► Toolkit MCP: disk_usage()           → 60 GB free, 12.1 TB used
  │
  ├─► Goose presents consolidated plan:
  │     Phase 1: Delete confirmed duplicates   (67 GB)
  │     Phase 2: Remove redundant emulators    (18 GB) → 85 GB freed
  │     Phase 3: Update MAME 0.228→0.273
  │     Phase 4: Update PCSX2 1.7→2.3
  │     Phase 5: Update RetroArch + 5 others
  │
  └─► User approves → Goose executes phase by phase with backups at each step
```

---

## File Structure

```
D:\hyperspin_toolkit\
├── main.py                          ← CLI entry point (8 command groups, 30+ commands)
├── mcp_bridge.py                    ← MCP server for Goose (14 tools)
├── config.yaml                      ← Toolkit configuration
├── requirements.txt                 ← All Python dependencies
│
├── engines\
│   ├── auditor.py                   ← Full/system audit logic
│   ├── backup.py                    ← Versioned backup/restore
│   ├── release_checker.py           ← GitHub releases API
│   ├── space_optimizer.py           ← Disk usage + duplicates
│   ├── external_tools.py            ← MAME, Igir, Flips wrappers
│   ├── update_manager.py            ← Safe update pipeline
│   ├── scanner.py                   ← System/emulator discovery
│   ├── ai_engine.py                 ← LM Studio/Ollama AI client
│   ├── llm_detector.py              ← VRAM-aware model scanner
│   ├── cli_anything_bridge.py       ← NL→CLI translation (MCP)
│   ├── nemoclaw_agents.py           ← 6 NemoClaw specialist agents (MCP)
│   └── openhands_bridge.py          ← OpenHands REST bridge (MCP)
│
├── core\
│   ├── config.py                    ← Config loader
│   ├── logger.py                    ← Structured logger + audit trail
│   └── database.py                  ← SQLite wrapper
│
├── setup\
│   ├── goose_setup.py               ← E2E stack validator + auto-fixer
│   └── install_goose.ps1            ← Goose v1.27.2 installer
│
└── docs\
    ├── ARCHITECTURE.md              ← This file
    ├── USER_GUIDE.md                ← How to use the full stack
    └── QUICK_REFERENCE.md           ← Command cheat sheet

%APPDATA%\Block\goose\config\
├── config.yaml                      ← Goose configuration (extensions + provider)
└── skills\
    ├── hyperspin-toolkit\SKILL.md   ← Master overview skill
    ├── hyperspin-audit\SKILL.md     ← Audit workflows
    ├── hyperspin-update\SKILL.md    ← Safe update pipeline
    ├── hyperspin-optimize\SKILL.md  ← Space optimization
    ├── hyperspin-backup\SKILL.md    ← Backup & rollback
    ├── hyperspin-releases\SKILL.md  ← GitHub release checker
    ├── hyperspin-mame\SKILL.md      ← MAME upgrade & repair
    ├── hyperspin-ai\SKILL.md        ← Local LLM assistant
    ├── hyperspin-vision\SKILL.md    ← GLM-4.6V media analysis
    ├── hyperspin-orchestrator\SKILL.md ← Master 4-agent coordinator
    └── hyperspin-cli-anything\SKILL.md ← CLI-Anything usage guide
```

---

## LM Studio Model Matrix (RTX 3090 Ti, 24 GB VRAM)

```
┌──────────────────────────────────────────────────────────────────────┐
│  VRAM Budget: 24 GB                                                  │
├────────────────────────────┬────────┬────────┬────────┬─────────────┤
│ Model                      │  Size  │  Ctx   │ RoPE  │ Use Case    │
├────────────────────────────┼────────┼────────┼────────┼─────────────┤
│ Devstral-24B Q4_K_M        │ 13.4 GB│  32K   │  32K  │ Goose main  │
│ Qwen3.5-9B Opus Q8         │  9.8 GB│ 128K   │ 256K  │ Fast reason │
│ Qwen3.5-27B Opus Q4_K_S    │ 14.5 GB│ 128K   │ 256K  │ Deep plan   │
│ Qwen3.5-35B A3B Q4_K_M     │ 19.7 GB│ 128K   │ 256K  │ Max quality │
│ GLM-4.6V-Flash Q8          │  9.3 GB│ 128K   │ 128K  │ Vision/art  │
└────────────────────────────┴────────┴────────┴────────┴─────────────┘
  defaultContextLength: 131072 (set in LM Studio settings.json)
  For 256K: set to 262144
```

---

## Dependency Graph

```
Goose v1.27.2
  ├── LM Studio ≥ 0.3.x   [REQUIRED — serves the LLM]
  │     └── Model loaded   [REQUIRED — Devstral-24B or Qwen3.5]
  ├── Python ≥ 3.10        [REQUIRED — runs all bridges]
  │     ├── httpx           [REQUIRED — LLM API + OpenHands calls]
  │     ├── click           [REQUIRED — CLI framework]
  │     └── rich            [REQUIRED — console output]
  ├── Ollama               [OPTIONAL — fallback LLM]
  └── Docker + OpenHands   [OPTIONAL — needed for batch file ops]
        └── docker.all-hands.dev/all-hands-ai/openhands:latest
```

---

## Setup Verification

```powershell
# Run full stack health check
python D:\hyperspin_toolkit\setup\goose_setup.py --e2e

# Expected output:
#   [OK] Python 3.x.x
#   [OK] main.py
#   [OK] mcp_bridge.py
#   [OK] cli_anything_bridge.py
#   [OK] nemoclaw_agents.py
#   [OK] openhands_bridge.py
#   [OK] 11/11 SKILL.md files
#   [OK] Goose config: 4 extensions wired
#   [OK] LM Studio: 1 model loaded
#   [OK] defaultContextLength = 131,072 (128K)
```
