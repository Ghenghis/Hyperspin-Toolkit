# HyperSpin Toolkit — Master Action Plan & Interactive TODO

> **Last Updated:** 2026-03-17 (v2 — Agentic AI + Arcade GUI Update)  
> **Status Legend:** ✅ Done | 🔄 In Progress | ⏳ Pending | ❌ Blocked  
> **New Phases:** Phase 8 (Agentic AI), Phase 9 (Arcade GUI), Phase 10 (Asset Audit)

---

## Phase 0: HDD Management & Environment Setup

### 0.1 Drive Labeling & Identification
- [ ] **Rename D: volume** to `Test_Hyperspin_Test` (PowerShell: `Set-Volume -DriveLetter D -NewFileSystemLabel "Test_Hyperspin_Test"`)
- [ ] **Verify drive_registry.json** is accurate after rename
- [ ] **Run CHKDSK on Warning drives** to diagnose filesystem issues:
  - [ ] `chkdsk D: /f /r /x` — Test HyperSpin drive (schedule if locked)
  - [ ] `chkdsk L: /f /r /x` — CORE - TYPE R drive
  - [ ] `chkdsk N: /f /r /x` — Batocera game partition
- [ ] **Document CHKDSK results** in per-drive profiles
- [ ] **Create physical labels** for external drive enclosures matching tags from `drive_registry.json`

### 0.2 Backup Operations (Priority Order)
- [ ] **Clone L: → H:** using HDD cloner (low-level clone, CORE - TYPE R → Retro_14tb)
  - [ ] Verify clone integrity after completion (file count + spot-check hashes)
  - [ ] Update `drive_registry.json` with clone timestamp
- [ ] **Research 22TB drives** for J: (20TB) backup — identify models + pricing
- [ ] **Evaluate N: backup options** — 2TB Batocera collection needs backup (Warning health)

### 0.3 Drive Index Generation
- [ ] **Build drive indexer engine** (`engines/drive_indexer.py`):
  - [ ] Scan all gaming drives and generate file manifests
  - [ ] Record file counts, total sizes, folder trees (depth-limited)
  - [ ] Store index in SQLite `drive_index` table
  - [ ] Auto-detect collection type using `drive_registry.json` identifiers
- [ ] **Generate per-drive index files** (JSON manifests saved to each drive root)
- [ ] **Create cross-drive duplicate detection** for ROM deduplication (feeds into M26)

### 0.4 NVIDIA OpenShell Setup
- [ ] **Verify prerequisites:**
  - [ ] Docker Desktop installed and running (WSL2 backend)
  - [ ] NVIDIA GPU driver up to date (RTX series)
  - [ ] NVIDIA Container Toolkit installed (`nvidia-ctk`)
  - [ ] WSL2 with GPU passthrough confirmed working
- [ ] **Install OpenShell v0.0.8** from [GitHub releases](https://github.com/NVIDIA/OpenShell/releases/tag/v0.0.8)
- [ ] **Create YAML sandbox policy** for HyperSpin Toolkit:
  - [ ] Allow read access to gaming drive mount paths
  - [ ] Allow write access to toolkit output directory only
  - [ ] Deny network access except for GitHub API (emulator update checks)
  - [ ] Deny access to system drives (C:, F:)
- [ ] **Test sandbox execution:**
  - [ ] Run `openshell sandbox create` with custom policy
  - [ ] Verify GPU acceleration (`nvidia-smi` inside container)
  - [ ] Test toolkit CLI inside sandbox
  - [ ] Test Ollama model access inside sandbox
- [ ] **Document OpenShell setup** in `docs/OPENSHELL_SETUP.md` ✅
- [ ] **Create docker-compose.yml** for toolkit + OpenShell integration

### 0.5 LLM Backend Stack
- [ ] **LM Studio (Default)** — verify running at `http://localhost:1234/v1`
  - [ ] Models dir: `C:\Users\Admin\.lmstudio\models`
  - [ ] Test OpenAI-compatible API connectivity
- [ ] **Ollama (Secondary)** — verify running at `http://localhost:11434/v1`
  - [ ] Models dir: `C:\Users\Admin\.ollama\models`
  - [ ] Pull required models: `llama3.1:8b`, `nomic-embed-text`
- [ ] **VLLM (Performance/Batch)** — install for multi-agent concurrent inference
  - [ ] `pip install vllm` (requires CUDA)
  - [ ] Configure at `http://localhost:8000/v1`
  - [ ] Benchmark: LM Studio vs Ollama vs VLLM throughput
- [ ] **Create `llm_config.yaml`** — provider priority chain + routing rules
- [ ] **Implement LLM router** in `engines/llm_router.py` — auto-select backend by task type

---

## Phase 1–2: Already Completed ✅

### Phase 1: Foundation (M1–M5)
- [x] M1 — CLI Scaffold & Config Loader
- [x] M2 — XML Parser & Validator
- [x] M3 — ROM/ISO Auditor
- [x] M4 — Media Asset Scanner
- [x] M5 — Backup & Recovery Engine

### Phase 2: Intelligence (M6–M11, M17, M22)
- [x] M6 — Plugin System & Marketplace
- [x] M7 — Emulator Health Check
- [x] M8 — Drive Transfer & Path Fixer
- [x] M9 — External Tool Integration (MAME, Igir, Flips, Skyscraper)
- [x] M10 — ROM Organization Engine
- [x] M11 — Update Pipeline (download, verify, snapshot, apply, rollback)
- [x] M17 — AI Natural Language Query
- [x] M22 — WebSocket Event Hub

---

## Phase 3: Safe Update Pipeline ✅

- [x] **M12 — Emulator Version Tracker & Updater** (27 tests)
  - [x] Engine: `engines/version_tracker.py`
  - [x] CLI: `releases` group commands
  - [x] MCP Bridge: 6 tool handlers
  - [x] Dashboard API: 6 endpoints
- [x] **M13 — Dependency Conflict Detector** (23 tests)
  - [x] Engine: `engines/dependency_detector.py`
  - [x] CLI: `deps` group commands
  - [x] MCP Bridge: 4 tool handlers
  - [x] Dashboard API: 4 endpoints
- [x] **M14 — Pre/Post Update Snapshot Verification** (14 tests)
  - [x] Engine: `engines/snapshot_verify.py`
  - [x] CLI: `snapshots` group commands
  - [x] MCP Bridge: 5 tool handlers
  - [x] Dashboard API: 5 endpoints
- [x] **M15 — Automated Rollback on Failure** (17 tests)
  - [x] Engine: `engines/auto_rollback.py`
  - [x] CLI: `rollback` group commands
  - [x] MCP Bridge: 7 tool handlers
  - [x] Dashboard API: 7 endpoints
- [x] **Full test suite: 364 passed**

---

## Phase 4: AI & Recommendation Engines

### M18 — AI Game Recommendation Engine ⏳
> *"If you like X, try Y" — collaborative filtering across collections*

- [ ] **Design recommendation model:**
  - [ ] Genre/tag-based similarity scoring
  - [ ] Cross-system recommendation (e.g., "liked Metroid on SNES → try Axiom Verge on PC")
  - [ ] Play frequency/favorites weighting (if available from HyperSpin stats)
- [ ] **Build engine:** `engines/game_recommender.py`
  - [ ] ROM metadata parser (extract genre, year, developer from XML/DB)
  - [ ] Similarity matrix computation
  - [ ] Recommendation generation with configurable filters
  - [ ] Integration with AI models (LM Studio/Ollama) for semantic matching
- [ ] **Write tests:** `tests/test_game_recommender.py`
- [ ] **Wire into CLI/MCP/Dashboard**

### M19 — NL Query System (Extended) ⏳
> *Extends M17 with richer filtering, cross-drive queries, and collection comparison*

- [ ] **Extend `engines/nl_query.py`:**
  - [ ] Multi-drive query support (query across D:, I:, K:, L:, N:)
  - [ ] Collection comparison queries ("what systems are on Batocera but not HyperSpin?")
  - [ ] ROM format queries ("what Switch games on J: are in .nsp format?")
  - [ ] Statistical queries ("which system has the most ROMs?")
- [ ] **Write tests:** `tests/test_nl_query_extended.py`
- [ ] **Wire into CLI/MCP/Dashboard**

### M20 — AI Troubleshooting Assistant ⏳
> *Error log parsing + fix suggestions*

- [ ] **Build engine:** `engines/troubleshooter.py`
  - [ ] Emulator log parser (parse MAME, RetroArch, Dolphin, PCSX2 logs)
  - [ ] Common error pattern database
  - [ ] AI-powered fix suggestion generation
  - [ ] Integration with M7 health check results
  - [ ] Automatic BIOS/ROM format mismatch detection
- [ ] **Write tests:** `tests/test_troubleshooter.py`
- [ ] **Wire into CLI/MCP/Dashboard**

---

## Phase 5: Dashboard UI & Management

### M23 — System Health Monitor Dashboard ⏳ (HIGH PRIORITY)
> *Live health dashboard UI showing all drives, emulators, and collection status*

- [ ] **Design dashboard layout:**
  - [ ] Drive health cards (using `drive_registry.json` data)
  - [ ] Real-time WebSocket updates (via M22 Event Hub)
  - [ ] Emulator version status (via M12)
  - [ ] Dependency conflict warnings (via M13)
  - [ ] Rollback history timeline (via M15)
- [ ] **Build frontend:**
  - [ ] React components for health cards, status panels, alerts
  - [ ] WebSocket connection for live updates
  - [ ] Drive identification by serial (letter-independent)
- [ ] **Create API endpoints** for aggregated health data
- [ ] **Write tests**

### M24 — Backup/Recovery Management UI ⏳
> *Visual backup timeline + one-click recovery*

- [ ] **Build backup timeline visualization**
- [ ] **Integrate with drive_registry.json** for drive-aware backup status
- [ ] **One-click clone verification** (hash comparison post-clone)
- [ ] **Clone scheduling** for automated periodic backups

### M25 — Update Manager UI ⏳
> *Visual update queue with approval workflow*

- [ ] **Build update queue panel** showing pending updates per emulator
- [ ] **Approval workflow** — review changes before applying
- [ ] **Rollback UI** — visual rollback with confirmation
- [ ] **Integration with M11 + M14 + M15** for full pipeline visibility

---

## Phase 6: Collection Management

### M26 — Duplicate ROM Cleanup ⏳
> *Cross-drive deduplication*

- [ ] **Build engine:** `engines/duplicate_cleaner.py`
  - [ ] Hash-based duplicate detection across drives
  - [ ] Priority rules (keep on primary, remove from backup)
  - [ ] Safe deletion with recycle bin support
  - [ ] Report generation
- [ ] **Wire into CLI/MCP/Dashboard**

### M27 — ROM Set Completion Tracker ⏳
> *Track which systems have complete/incomplete ROM sets*

- [ ] **Build engine:** `engines/completion_tracker.py`
  - [ ] Compare local ROMs against DAT files (No-Intro, TOSEC, Redump)
  - [ ] Per-system completion percentage
  - [ ] Missing ROM reports
  - [ ] Cross-drive aggregation
- [ ] **Wire into CLI/MCP/Dashboard**

### M31 — Multi-Drive Collection Sync ⏳
> *Synchronize collections across multiple drives*

- [ ] **Build engine:** `engines/drive_sync.py`
  - [ ] Drive discovery using `drive_registry.json`
  - [ ] Differential sync (only copy changes)
  - [ ] Conflict resolution for divergent collections
  - [ ] Sync profiles (e.g., "sync HyperSpin D: ↔ I:")
  - [ ] Switch ROM migration from J: to active drives (format validation)
- [ ] **Wire into CLI/MCP/Dashboard**

### M33 — Theme/Media Downloader ⏳
> *Download missing themes, videos, bezels, box art*

- [ ] **Build engine:** `engines/media_downloader.py`
  - [ ] HyperSpin theme repositories integration
  - [ ] Batocera theme/decoration downloader
  - [ ] Missing media detection (cross-reference with M4 scan results)
  - [ ] Parallel download with progress tracking
- [ ] **Wire into CLI/MCP/Dashboard**

---

## Phase 7: Advanced Features

### M28 — Online Research Agent ⏳
> *Automated ROM/emulator information lookup*

- [ ] **Build engine:** `engines/research_agent.py`
- [ ] **Integration with web search APIs** for ROM compatibility info
- [ ] **Emulator configuration lookup**

### M29 — Automated Report Generator ⏳
> *Generate comprehensive collection reports*

- [ ] **Build engine:** `engines/report_generator.py`
  - [ ] HTML/PDF report generation
  - [ ] Per-drive summary reports
  - [ ] Cross-collection comparison reports
  - [ ] Export to Markdown

### M32 — Performance Benchmarking ⏳
> *Emulator performance metrics*

- [ ] **Build engine:** `engines/benchmarker.py`
- [ ] **Emulator startup time measurement**
- [ ] **ROM loading performance testing**
- [ ] **Drive I/O benchmarking** (USB vs NVMe performance comparison)

### M34 — Full Ecosystem Health Score ⏳
> *Aggregated health score across all drives and collections*

- [ ] **Build engine:** `engines/ecosystem_health.py`
  - [ ] Weighted scoring: drive health, emulator status, ROM completeness, backup coverage
  - [ ] Integration with all M7/M12/M13/M14/M15 results
  - [ ] Trend tracking over time
  - [ ] Alerts and recommendations
- [ ] **Wire into CLI/MCP/Dashboard**

### M35 — Agentic Workflow Orchestrator ⏳ (Capstone)
> *End-to-end automated workflows combining all engines*

- [ ] **Build orchestrator:** `engines/orchestrator.py`
  - [ ] Workflow definitions (YAML-based)
  - [ ] Step execution with dependency resolution
  - [ ] Error handling with automatic rollback
  - [ ] Parallel execution where safe
- [ ] **Pre-built workflows:**
  - [ ] Full ecosystem audit (M3+M4+M7+M12+M13+M34)
  - [ ] Safe update pipeline (M14→M11→M15→M12)
  - [ ] New drive setup (format→clone→verify→index)
  - [ ] Collection migration (M31+M8+M14)
- [ ] **Integration with NVIDIA OpenShell** for sandboxed execution

---

## Phase 8: Agentic AI Integration ⏳ (NEW — HIGH PRIORITY)

> **See:** `docs/AGENTIC_INTEGRATION.md` for full architecture and orchestration flow  
> **Goal:** Goose + OpenHands control NemoClaw agents seamlessly, using Skills for discovery

### 8.1 Goose — Primary Orchestrator
- [ ] **Install Goose v1.27.2** from [GitHub](https://github.com/block/goose/releases/tag/v1.27.2)
  - [ ] `winget install Block.Goose` or download binary
  - [ ] Configure LM Studio as default provider: `goose configure --provider lmstudio`
- [ ] **Register HyperSpin Toolkit as MCP server:**
  - [ ] `goose mcp add hyperspin-toolkit -- python D:\hyperspin_toolkit\mcp_bridge.py`
  - [ ] Verify Goose can call all existing MCP tools (M12-M15 handlers)
- [ ] **Create custom Goose extensions:**
  - [ ] Drive management extension (wraps `engines/drive_indexer.py`)
  - [ ] ROM audit extension (wraps `engines/rom_auditor.py`)
  - [ ] Asset scan extension (wraps `engines/asset_auditor.py`)
- [ ] **Test Goose ↔ MCP Bridge** end-to-end with real commands
- [ ] **Document Goose setup** with custom distributions config

### 8.2 OpenHands — Coding & Development Agent
- [ ] **Install OpenHands Docker image:**
  - [ ] `docker pull ghcr.io/openhands/openhands:latest`
  - [ ] Configure with LM Studio backend (`LLM_BASE_URL=http://host.docker.internal:1234/v1`)
- [ ] **Mount workspace volume:** `D:\hyperspin_toolkit → /workspace`
- [ ] **Test autonomous coding tasks:**
  - [ ] Run existing test suite inside OpenHands sandbox
  - [ ] Generate a new engine file from spec
  - [ ] Debug a failing test
- [ ] **Integrate with Goose:** Goose delegates coding tasks to OpenHands
- [ ] **Document OpenHands setup** for local LLM usage

### 8.3 NemoClaw — Agent Sandbox Orchestration
- [ ] **Clone NemoClaw:** `git clone https://github.com/NVIDIA/NemoClaw.git`
- [ ] **Install dependencies:** `npm install`
- [ ] **Override default inference** from NVIDIA cloud to local LM Studio
- [ ] **Create agent blueprints:**
  - [ ] `blueprints/rom-auditor.yaml` — read-only access to all gaming drives
  - [ ] `blueprints/asset-scanner.yaml` — read-only drives + write to output
  - [ ] `blueprints/emulator-health.yaml` — read-only + write to D: test drive
  - [ ] `blueprints/backup-manager.yaml` — read-write to H: backup target only
- [ ] **Define OpenShell policies** per blueprint using `drive_registry.json`
- [ ] **Test sandbox lifecycle:** `nemoclaw onboard`, `nemoclaw status`, `nemoclaw destroy`

### 8.4 CLI-Anything — Software-to-Agent Bridge
> **Already on D:\CLI-Anything** — existing CLIs: audacity, blender, comfyui, gimp, inkscape, etc.

- [ ] **Generate new CLIs for this project:**
  - [ ] `cli-anything-hyperspin` — control HyperSpin.exe frontend
  - [ ] `cli-anything-rocketlauncher` — control RocketLauncher backend
  - [ ] `cli-anything-mame` — control MAME emulator
  - [ ] `cli-anything-retroarch` — control RetroArch core system
  - [ ] `cli-anything-lmstudio` — control LM Studio inference
  - [ ] `cli-anything-ollama` — control Ollama inference
- [ ] **Verify SKILL.md generation** for each CLI (agent-discoverable)
- [ ] **Register Skills with Goose:** `goose skill load cli-anything-*`
- [ ] **Test agent-driven software control** through Skills

### 8.5 Orchestration Workflows
- [ ] **Create YAML workflow definitions:**
  - [ ] `workflows/full-audit.yaml` — ROM + Asset + Health audit across all drives
  - [ ] `workflows/safe-update.yaml` — snapshot → update → verify → rollback
  - [ ] `workflows/collection-sync.yaml` — diff + transfer across drives
  - [ ] `workflows/asset-catalog.yaml` — scan + classify + score all game assets
- [ ] **Implement Goose ↔ NemoClaw ↔ OpenHands communication pipeline**
- [ ] **Add automatic LLM backend selection** (LM Studio for interactive, VLLM for batch)
- [ ] **End-to-end test:** User request → Goose → NemoClaw agents → results

### 8.6 Security & Policies
- [ ] **Drive access policies** mapped from `drive_registry.json`:
  - [ ] I:, K:, L:, J: — read-only from all agents
  - [ ] D: — read-write for testing agents only
  - [ ] H: — write for backup agents only
  - [ ] C:, F: — denied to all agents
- [ ] **All inference stays local** — no cloud API calls
- [ ] **Serial-based drive verification** before any disk write operation
- [ ] **Agent output isolation** — all writes to `D:\HyperSpin_Toolkit_Output\`

---

## Phase 9: Arcade GUI — SOTA C#/WPF Interface ⏳ (NEW)

> **See:** `docs/ARCADE_GUI_PLAN.md` for full design, effects, and asset mapping  
> **Goal:** Every page of the toolkit looks like a premium arcade cabinet interface  
> **Stack:** C# / .NET 8 / WPF / LibVLCSharp / SharpDX / CefSharp

### 9.1 Project Setup
- [ ] **Create .NET 8 WPF solution** at `D:\hyperspin_toolkit\gui\`
  - [ ] `HyperSpinToolkit.App` (main WPF app)
  - [ ] `HyperSpinToolkit.Core` (shared library)
  - [ ] `HyperSpinToolkit.Tests` (unit tests)
- [ ] **Install NuGet packages:**
  - [ ] LibVLCSharp.WPF (video backgrounds)
  - [ ] LottieSharp (converted SWF animations)
  - [ ] CefSharp.Wpf (fallback SWF rendering)
  - [ ] XInputDotNet (gamepad/joystick support)
- [ ] **Add arcade fonts:** Press Start 2P, Orbitron, JetBrains Mono

### 9.2 Theme Engine & Visual System
- [ ] **Implement `ArcadeThemeEngine`** — dynamically loads assets from all HDDs:
  - [ ] D:\Arcade\Media (301K PNGs, 47K videos, 20K audio, 8K SWF themes)
  - [ ] K:\Arcade\menu-art (fanart, flyers, marquees, snaps, themes)
  - [ ] L:\CORE - TYPE R\collections\Main (system_artwork, menu)
  - [ ] N:\themes, N:\decorations (Batocera assets)
- [ ] **Neon color palette** — NeonBlue, NeonPink, NeonGreen, NeonYellow, NeonPurple
- [ ] **Global ArcadeTheme.xaml** with dark cabinet backgrounds + glow effects

### 9.3 Custom Arcade Controls
- [ ] **ArcadeButton** — neon glow on hover, pulse on click, sound effect
- [ ] **WheelCarousel** — 3D spinning wheel with game art (à la HyperSpin)
- [ ] **NeonGauge** — arcade-style meter for drive health, completion %
- [ ] **LedIndicator** — multi-color LED for status (green/yellow/red)
- [ ] **ScoreCounter** — animated number roller for statistics
- [ ] **CrtTerminal** — scanline terminal for agent console
- [ ] **VideoBackground** — LibVLC video loop from game preview videos
- [ ] **ParticleCanvas** — background particle effects

### 9.4 HLSL Shader Effects
- [ ] **CRT Scanline Effect** — pixel shader for retro CRT look
- [ ] **Neon Glow Effect** — bloom shader for button/text glow
- [ ] **Pixel Dissolve Effect** — page transition shader

### 9.5 Pages (All Arcade-Themed)
- [ ] **Dashboard** — system wheel, drive health gauges, neon stats, video background
- [ ] **Collection Browser** — HyperSpin-style spinning wheel + video previews
- [ ] **Drive Manager** — LED indicators, arcade gauges per drive
- [ ] **Agent Console** — CRT scanline terminal, real-time agent status
- [ ] **Asset Gallery** — grid browse/search all 301K+ game assets
- [ ] **Update Center** — arcade loading screen progress bars
- [ ] **ROM Audit** — Pac-Man-style completion meters per system
- [ ] **Backup Control** — pixel-art animated transfer progress
- [ ] **Settings** — retro options menu with joystick navigation
- [ ] **AI Chat** — arcade-style chat bubbles with scanline text

### 9.6 Agent Integration
- [ ] **AgentBridgeService** — WebSocket connection to Goose/MCP Bridge
- [ ] **Real-time agent status** in HUD overlay
- [ ] **Agent results visualization** (audit reports, recommendations)
- [ ] **Natural language chat** to Goose through AiChatView

### 9.7 Gamepad/Joystick Support
- [ ] **Full gamepad navigation** — D-pad, ABXY, triggers, sticks
- [ ] **Joystick analog scrolling** for wheel/list navigation
- [ ] **Button mapping configuration** in Settings page

### 9.8 SWF Theme Conversion Pipeline
- [ ] **JPEXS CLI → Lottie JSON** for top 100 most-used themes
- [ ] **FFmpeg batch → MP4** for remaining SWF themes
- [ ] **Static PNG snapshots** for thumbnails/previews
- [ ] **CefSharp fallback** for complex interactive themes

---

## Phase 10: Asset Audit Engine ⏳ (NEW)

> **Goal:** Scan all gaming HDDs and build a searchable index of every visual, audio, and animation asset for GUI theming and agent-driven curation

### 10.1 Asset Auditor Engine
- [ ] **Build `engines/asset_auditor.py`:**
  - [ ] Scan all `Media/`, `menu-art/`, `system_artwork/`, `themes/` directories
  - [ ] Index: path, type, format, dimensions, file size, drive tag
  - [ ] Detect asset types: wheel_art, background, box_art, theme_anim, video, audio, fanart, marquee, flyer, snap, bezel
  - [ ] Calculate quality score per asset (resolution, file size, format)
  - [ ] Tag assets by GUI page relevance
- [ ] **Generate `asset_index.json`** (or SQLite) — searchable asset database
- [ ] **Create optimized thumbnail cache** (resized PNGs for fast GUI browsing)
- [ ] **Write tests:** `tests/test_asset_auditor.py`

### 10.2 Cross-Drive Asset Statistics
- [ ] **Total asset count by type** across all drives:
  - [ ] Currently: 301K PNGs, 47K videos, 20K audio, 8K SWF themes
- [ ] **Per-system asset coverage** — which systems have complete media vs gaps
- [ ] **Best assets per system** — highest quality wheel art, backgrounds, videos
- [ ] **Missing media report** — systems with ROMs but no media assets

### 10.3 GUI Asset Recommendations
- [ ] **Dashboard background candidates** — top-rated animated themes or video loops
- [ ] **Per-page theme mapping** — best assets for each GUI page
- [ ] **Dynamic theme rotation** — periodically cycle through top assets
- [ ] **User favorites** — allow pinning preferred assets per page

### 10.4 Agent-Driven Curation
- [ ] **Asset Scanner NemoClaw agent** — runs in sandbox, read-only drive access
- [ ] **AI-powered classification** — use VLLM for batch image analysis
- [ ] **Duplicate asset detection** — find identical assets across drives
- [ ] **Asset quality improvement suggestions** — upscale candidates, missing formats

---

## Switch Game Integration (From J: 20TB Backup)

> User noted Switch games on J: could be added to a drive with room + proper emulator.

- [ ] **Scan J: for Switch ROMs** — identify formats (.nsp, .xci, .nsz)
- [ ] **Identify target drive** — which active collection drive has capacity?
  - K: has 178 GB free, L: has 161 GB free, I: has 55 GB free → none have much room
  - May need to wait for drive upgrades (14-18TB)
- [ ] **Check emulator availability:**
  - [ ] Yuzu/Ryujinx/Suyu on HyperSpin drives (D:/I:)?
  - [ ] Switch emulator on Batocera (N:)?
  - [ ] Switch emulator in CORE - TYPE R (L:)?
- [ ] **Validate ROM format compatibility** with available emulators
- [ ] **Plan migration** once drive capacity available

---

## Hardware Upgrade Roadmap

### Drive Upgrades (12TB → 14-22TB)

| Current | Tag                  | Target Size | Priority | Notes                          |
| ------- | -------------------- | ----------- | -------- | ------------------------------ |
| D: 12TB | TEST_HYPERSPIN       | 14-18TB     | Low      | Testing only — upgrade last    |
| I: 12TB | PRIMARY_HYPERSPIN    | 14-18TB     | Medium   | Active gaming — needs downtime |
| K: 12TB | HYPERSPIN_ATTRACTION | 14-18TB     | Medium   | Backup — can upgrade anytime   |
| L: 12TB | CORE_TYPE_R          | 14-18TB     | High     | User favorite, Warning health  |

### New Drives Needed

| Purpose                              | Min Size    | Priority | Status         |
| ------------------------------------ | ----------- | -------- | -------------- |
| Backup for J: (20TB)                 | 22TB        | Medium   | ❌ Not acquired |
| Backup for N: (2TB Batocera)         | 4TB         | Low      | ❌ Not acquired |
| Upgrade replacements for 12TB drives | 14-18TB × 4 | Medium   | ❌ Planning     |

### HDD Clone Procedure
1. Connect new drive + old drive to HDD cloner
2. Perform low-level sector clone
3. Verify clone with `engines/snapshot_verify.py` compare
4. Update `drive_registry.json` with new serial/model
5. Physical label the new drive
6. Retire or repurpose old drive

---

## Testing Strategy

### Testing Drive: D: (Test_Hyperspin_Test)
All toolkit testing should target D: exclusively:
- M11 update pipeline tests
- M12 version tracker scans
- M13 dependency detection
- M14 snapshot capture/verify
- M15 rollback operations
- M31 sync operations (D: ↔ test target)
- Phase 8 agent sandbox testing (NemoClaw agents write to D: only)
- Phase 10 asset audit scanning (read-only from all drives)

### Test Isolation Rules
1. **NEVER** run destructive operations on I:, K:, L:, or J:
2. **ALWAYS** use `--emu-root D:\Arcade` for testing
3. **VERIFY** drive letter before any write operation
4. Use `drive_registry.json` serial check to confirm target drive
5. **All agent output** goes to `D:\HyperSpin_Toolkit_Output\`
6. **NemoClaw sandbox policies** enforce drive access rules

### Automated Test Suite
- Current: **364+ tests passing** (including 22 drive_indexer tests)
- Target: 600+ tests after Phase 4-10 milestones
- Agent integration tests: end-to-end Goose → NemoClaw → result validation
- GUI tests: WPF control rendering, theme engine, asset loading

---

## Quick Command Reference

```powershell
# === HDD Management ===
Set-Volume -DriveLetter D -NewFileSystemLabel "Test_Hyperspin_Test"
chkdsk D: /f /r /x
chkdsk L: /f /r /x
chkdsk N: /f /r /x

# === Toolkit CLI ===
python -m pytest tests/ -v --tb=short
python main.py releases scan-versions --emu-root "D:\Arcade"
python main.py deps scan --emu-root "D:\Arcade"
python main.py snapshots capture "D:\Arcade\MAME" --name "mame-pre-update"
python main.py rollback post-update MAME --emu-root "D:\Arcade"

# === LLM Backends ===
# LM Studio (default) — already at http://localhost:1234/v1
# Ollama
ollama serve                              # Start Ollama
ollama pull llama3.1:8b                   # Pull model
# VLLM (batch/perf mode)
python -m vllm.entrypoints.openai.api_server --model <path> --port 8000

# === Agentic AI Stack ===
# Goose
winget install Block.Goose
goose configure --provider lmstudio --base-url http://localhost:1234/v1
goose mcp add hyperspin-toolkit -- python D:\hyperspin_toolkit\mcp_bridge.py

# OpenHands
docker pull ghcr.io/openhands/openhands:latest
docker run -it --rm -e LLM_BASE_URL="http://host.docker.internal:1234/v1" -v D:\hyperspin_toolkit:/workspace -p 3000:3000 ghcr.io/openhands/openhands:latest

# NemoClaw
git clone https://github.com/NVIDIA/NemoClaw.git C:\tools\NemoClaw
nemoclaw onboard --blueprint D:\hyperspin_toolkit\blueprints\rom-auditor.yaml

# OpenShell
openshell sandbox create --policy toolkit-policy.yaml

# CLI-Anything (already at D:\CLI-Anything)
# Generate new CLIs from software executables

# === Arcade GUI ===
# Build and run (after .NET 8 solution created)
dotnet build D:\hyperspin_toolkit\gui\HyperSpinToolkit.sln
dotnet run --project D:\hyperspin_toolkit\gui\HyperSpinToolkit.App
```

---

## Documentation Index

| Document                | Path                          | Description                           |
| ----------------------- | ----------------------------- | ------------------------------------- |
| **Master TODO**         | `docs/TODO.md`                | This file — comprehensive action plan |
| **HDD Inventory**       | `docs/HDD_INVENTORY.md`       | All drives, roles, health, serials    |
| **Backup Strategy**     | `docs/BACKUP_STRATEGY.md`     | Clone procedures, upgrade paths       |
| **OpenShell Setup**     | `docs/OPENSHELL_SETUP.md`     | NVIDIA sandbox configuration          |
| **Agentic Integration** | `docs/AGENTIC_INTEGRATION.md` | Goose+OpenHands+NemoClaw architecture |
| **Arcade GUI Plan**     | `docs/ARCADE_GUI_PLAN.md`     | C#/WPF design, effects, assets        |
| **Drive Registry**      | `drive_registry.json`         | Serial→label mapping, metadata        |
