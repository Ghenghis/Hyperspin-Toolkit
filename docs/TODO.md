# HyperSpin Toolkit — Master Action Plan & Interactive TODO

> **Last Updated:** 2026-03-17 (v4 — Agentic stack installation + dashboard fixes)  
> **Status Legend:** ✅ Done | 🔄 In Progress | ⏳ Pending | ❌ Blocked  
> **All 15 Phases Complete:** Foundation through KINHANK Variant Management (M1–M66)

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

## Phase 4: AI & Recommendation Engines ✅

### M18 — AI Game Recommendation Engine ✅
- [x] **Engine built:** `engines/game_recommender.py` (520 lines)
- [x] Genre taxonomy (18 categories), era classification, similarity scoring
- [x] MCP tools: `recommend_similar_games`, `recommend_by_preference`, `discover_hidden_gems`, `analyze_game_collection`, `genre_cluster_report`
- [x] Tests passing

### M19 — NL Query System (Extended) ✅
- [x] **Engine:** `engines/nl_query.py` + `engines/ai_engine.py` NLQueryEngine
- [x] SQL generation from natural language, provider selection, audit logging
- [x] Dashboard API: `POST /api/ai/query`, `GET /api/ai/recommend`, `GET /api/ai/report`
- [x] MCP tools: `nl_query`, `ai_recommend_model`, `ai_full_report`

### M20 — AI Troubleshooting Assistant ✅
- [x] **Engine built:** `engines/troubleshooter.py` (580 lines)
- [x] 10-category common issue KB, regex pattern matching, error log parser
- [x] MCP tools: `diagnose_problem`, `diagnose_system`, `parse_error_log`, `known_issues_kb`
- [x] Tests passing

---

## Phase 5: Dashboard UI & Management ✅

### M23 — System Health Monitor Dashboard ✅
- [x] **`dashboard/templates/health.html`** wired to all backend APIs
- [x] Real-time WebSocket refresh on update/rollback/snapshot/scan events
- [x] Health summary, emulator health, dependency conflicts, version tracking, snapshots, rollbacks, AI status, events

### M24 — Backup/Recovery Management UI ✅
- [x] **`dashboard/templates/backups.html`** wired to backup/snapshot/rollback APIs
- [x] Create backup + capture snapshot forms functional
- [x] Real-time WebSocket refresh on backup/snapshot/rollback events

### M25 — Update Manager UI ✅
- [x] **`dashboard/templates/updates.html`** wired to update/version/rollback APIs
- [x] Full update pipeline: check → scan → stage → quarantine → apply/reject
- [x] Real-time WebSocket refresh on update/rollback/snapshot events

---

## Phase 6: Collection Management ✅

### M26 — Duplicate ROM Detection & Cleanup ✅
- [x] **Engine:** `engines/duplicate_detector.py` (500 lines)
- [x] CRC32/MD5 hashing, region variant detection, safe quarantine cleanup
- [x] MCP tools: `detect_duplicate_roms`, `detect_region_variants`, `duplicate_space_savings`

### M27 — ROM Set Completion Tracker ✅
- [x] **Engine:** `engines/rom_completion.py` (530 lines)
- [x] DAT file parsing, per-system completion %, priority scoring, collection goals
- [x] MCP tools: `check_rom_completion`, `completion_overview`, `get_missing_roms`, `set_collection_goal`, `check_goal_progress`

### M31 — Multi-Drive Collection Sync ✅
- [x] **Engine:** `engines/drive_sync.py` (480 lines)
- [x] Delta diff, conflict strategies, orphan cleanup, dry-run mode
- [x] MCP tools: `create_sync_pair`, `list_sync_pairs`, `analyze_sync_diff`, `execute_sync`, `sync_status`

### M33 — Theme/Media Downloader ✅
- [x] **Engine:** `engines/theme_downloader.py` (480 lines)
- [x] 10 media types, 6 known sources, download queue with SQLite, quality verification
- [x] MCP tools: `scan_missing_media`, `queue_media_downloads`, `download_stats`, `list_media_sources`

---

## Phase 7: Advanced Features ✅

### M28 — Online Research Agent ✅
- [x] **Engine:** `engines/research_agent.py` (430 lines)
- [x] 14 emulator GitHub release tracking, game/system research, community tips
- [x] MCP tools: `check_emulator_updates`, `research_game`, `research_system`, `store_community_tip`, `list_known_emulators`

### M29 — Automated Report Generator ✅
- [x] **Engine:** `engines/report_generator.py` (470 lines)
- [x] Markdown/JSON/HTML output, arcade-themed HTML with neon styling
- [x] MCP tools: `generate_health_report`, `generate_system_report`, `list_reports`

### M32 — Performance Benchmarking ✅
- [x] **Engine:** `engines/perf_benchmark.py` (460 lines)
- [x] Launch time measurement, composite scoring, emulator rankings, SQLite persistence
- [x] MCP tools: `record_benchmark`, `rank_emulators`, `benchmark_summary`, `performance_history`

### M34 — Full Ecosystem Health Score ✅
- [x] **Engine:** `engines/health_score.py` (500 lines)
- [x] 8 weighted subsystems, A+ to F grading, trend analysis, AI narrative
- [x] MCP tools: `calculate_health_score`, `health_score_history`, `health_score_breakdown`

### M35 — Agentic Workflow Orchestrator ✅
- [x] **Engines:** `engines/nemoclaw_agents.py`, `engines/openhands_bridge.py`, `engines/cli_anything_bridge.py`
- [x] 4 agent blueprints, 4 workflow definitions, MCP bridge (70+ tools)
- [x] `engines/security_orchestrator.py` for drive access policies and workflow runner

---

## Phase 8: Agentic AI Integration ✅

### 8.1 Goose — Primary Orchestrator ✅
- [x] `setup/goose_setup.py` (417 lines) full stack validator with 9 check categories
- [x] E2E smoke tests across all 4 MCP bridges
- [x] MCP tools: `goose_validate_stack`, `goose_e2e_test`

### 8.2 OpenHands — Coding & Development Agent ✅
- [x] `engines/openhands_bridge.py` (396 lines) REST client, session management
- [x] MCP tools: `openhands_status`, `openhands_run_task`, `openhands_update_ini`

### 8.3 NemoClaw — Agent Sandbox Orchestration ✅
- [x] `engines/nemoclaw_agents.py` (548 lines) 6 specialist agents
- [x] MCP tools: `nemoclaw_delegate`, `nemoclaw_plan`, `nemoclaw_list_agents`

### 8.4 CLI-Anything — Software-to-Agent Bridge ✅
- [x] `engines/cli_anything_bridge.py` (408 lines) 30+ static command mappings
- [x] MCP tools: `cli_resolve`, `cli_run`

### 8.5 Orchestration Workflows ✅
- [x] 4 YAML workflow definitions in `workflows/`
- [x] Goose ↔ NemoClaw ↔ OpenHands communication pipeline implemented

### 8.6 Security & Policies ✅
- [x] `engines/security_orchestrator.py` (310 lines) drive access policies, serial verification
- [x] Local inference enforcement, YAML workflow runner with approval queue
- [x] MCP tools: `get_drive_policies`, `check_drive_access`, `verify_local_inference`, `start_workflow`, etc.

### 8.7 External Tool Installation Status (Updated 2026-03-17)
- [x] **Goose v1.27.2 CLI** — installed at `%LOCALAPPDATA%\Goose\bin\goose.exe`, PATH updated
- [x] **Goose config.yaml** — 4 MCP extensions wired + LM Studio provider
- [x] **Goose skills** — 11 skill files in `%APPDATA%\Block\goose\config\skills\`
- [x] **CLI-Anything** — installed at `D:\CLI-Anything` (23+ tools)
- [x] **NemoClaw** — cloned to `C:\tools\NemoClaw` (npm deps need retry)
- [x] **Ollama v0.18.1** — running, 25 models, API at `localhost:11434`
- [x] **LM Studio** — running, 63 models, API at `localhost:1234`
- [x] **LM Studio mcp.json** — all 4 MCP bridges wired
- [x] **MCP Bridge E2E** — all 4 bridges verified (236+2+3+5 = 246 tools)
- [x] **OpenHands Docker** — `ghcr.io/openhands/openhands:latest` pulled successfully
- [x] **NemoClaw npm** — `node-llama-cpp` native build fails on Windows (known), Python bridge works independently
- [x] **Full validation** — `python setup/goose_setup.py --e2e` → 35/35 checks + 4/4 E2E smoke tests passed
- [x] **goose_setup.py fixes** — fixed `core.config` import crash + E2E initialize handshake

> **See:** `PROGRESS_AGENTIC_INSTALL.md` for detailed commands and paths

---

## Phase 9: Arcade GUI — SOTA C#/WPF Interface ✅

> **See:** `docs/ARCADE_GUI_PLAN.md` for full design, effects, and asset mapping

### 9.1–9.8 All Complete ✅
- [x] **Engine:** `engines/theme_engine.py` (620 lines) — asset discovery across all HDDs, quality scoring, thumbnail caching
- [x] **Engine:** `engines/swf_converter.py` (520 lines) — JPEXS→Lottie, FFmpeg→MP4, PNG snapshots, CefSharp fallback
- [x] Theme engine MCP tools: `discover_theme_assets`, `theme_coverage`, `best_assets_for_page`, `convert_swf_batch`, `conversion_status`
- [x] SWF converter MCP tools: `swf_to_lottie`, `swf_to_video`, `swf_snapshot`, `batch_convert_swf`, `swf_conversion_stats`
- [x] GUI architecture designed: 10 arcade-themed pages, 8 custom controls, 3 HLSL shaders, gamepad support
- [x] Tests: `tests/test_theme_engine.py`, `tests/test_swf_converter.py`

---

## Phase 10: Asset Audit Engine ✅

### 10.1–10.4 All Complete ✅
- [x] **Engine:** `engines/asset_auditor.py` (580 lines) — multi-drive scanning, 11 asset types, quality scoring, SQLite index
- [x] Cross-drive statistics, per-system coverage, missing media reports
- [x] GUI asset recommendations, per-page theme mapping, dynamic rotation
- [x] MCP tools: `scan_assets`, `asset_statistics`, `best_assets_per_system`, `missing_media_report`, `asset_quality_audit`
- [x] Tests: `tests/test_asset_auditor.py`

---

## Phase 11: Data Pipeline & Cross-Platform ✅

> **Milestones:** M53–M58 — all engines built and tested

### 11.1 Drive Indexer & Manifest Engine (M53) ✅
- [x] **Engine:** `engines/drive_indexer.py` (540 lines) — cross-HDD scanning, CRC32/MD5 hashing, SQLite index, JSON manifests, auto-detect collection type
- [x] MCP tools: `index_drive`, `search_drive_index`, `drive_manifest`, `compare_drives`

### 11.2 Metadata Scraping Engine (M54) ✅
- [x] **Engine:** `engines/metadata_scraper.py` (680 lines) — ScreenScraper, TheGamesDB, IGDB, ArcadeDB clients
- [x] Rate limiting, retry logic, credential management, SQLite `game_metadata` table
- [x] MCP tools: `scrape_game_metadata`, `scrape_system_media`, `metadata_coverage`, `metadata_search`

### 11.3 BIOS Management & Verification (M55) ✅
- [x] **Engine:** `engines/bios_manager.py` (550 lines) — BIOS scanning, checksum verification, emulator mapping
- [x] Known-good checksums from libretro System.dat + Batocera es_bios.xml
- [x] MCP tools: `scan_bios`, `verify_bios`, `bios_health_report`, `missing_bios`

### 11.4 DAT File ROM Set Verification (M56) ✅
- [x] **Engine:** `engines/dat_verifier.py` (600 lines) — No-Intro/Redump/TOSEC DAT parser, 1G1R curation
- [x] CRC32/MD5/SHA1 verification, region priority config, completion reports
- [x] MCP tools: `verify_romset`, `dat_completion`, `find_missing_roms`, `find_extra_roms`

### 11.5 HyperSpin Settings Manager (M57) ✅
- [x] **Engine:** `engines/hyperspin_settings.py` (520 lines) — INI read/write/validate, preset configs
- [x] MCP tools: `read_hyperspin_settings`, `write_hyperspin_settings`, `validate_settings`, `apply_preset`

### 11.6 Cross-Frontend Import/Export (M58) ✅
- [x] **Engine:** `engines/frontend_converter.py` (560 lines) — HyperSpin ↔ ES ↔ LaunchBox ↔ AM ↔ Pegasus
- [x] Media path remapping, batch conversion, cross-frontend diff
- [x] MCP tools: `convert_gamelist`, `compare_frontends`, `remap_media_paths`, `batch_convert`

---

## Phase 12: RocketLauncher Deep Integration ✅

> **Milestones:** M59–M60 — all engines built with dashboard API + MCP tools

### 12.1 Fade, Bezel & Pause Manager (M59) ✅
- [x] **Engine:** `engines/rl_media_manager.py` (936 lines)
- [x] Multi-layer fade scanning (Layer 1-4), bezel overlay + background validation, pause screen assets
- [x] Per-system coverage reports with severity-tagged issues
- [x] Dashboard API: `/api/rl/media/coverage`, `/api/rl/media/system/{system}`, `/api/rl/media/missing/{system}`, `/api/rl/media/fade/{system}`, `/api/rl/media/bezels/{system}`, `/api/rl/media/pause/{system}`
- [x] MCP tools: `rl_media_coverage`, `rl_system_media`, `rl_missing_media`, `rl_scan_fade`, `rl_scan_bezels`, `rl_scan_pause`

### 12.2 Keymapper, Statistics & MultiGame (M60) ✅
- [x] **Engine:** `engines/rl_stats_keymapper.py` (746 lines)
- [x] RL statistics XML parsing, keymapper profile scanning (AHK/Xpadder/JoyToKey), MultiGame INI validation, 7z settings
- [x] Dashboard API: `/api/rl/stats/{system}`, `/api/rl/most-played`, `/api/rl/keymappers`, `/api/rl/multigame/{system}`, `/api/rl/7z-settings`, `/api/rl/integration-report`
- [x] MCP tools: `rl_system_stats`, `rl_most_played`, `rl_keymappers`, `rl_multigame`, `rl_7z_settings`, `rl_integration_report`

---

## Phase 13: Automation & Operations ✅

> **Milestones:** M61–M63 — all engines built and tested

### 13.1 Scheduler & Notification System (M61) ✅
- [x] **Engine:** `engines/scheduler.py` (580 lines) — cron-like scheduling, maintenance cycles, Windows toast + in-app notifications
- [x] Periodic audits, scheduled backups, automated update checks, drive health monitoring
- [x] MCP tools: `schedule_task`, `list_scheduled_tasks`, `cancel_task`, `run_maintenance_cycle`, `send_notification`

### 13.2 Agent Memory, Learning & Knowledge Base (M62) ✅
- [x] **Engine:** `engines/agent_memory.py` (500 lines) — SQLite persistence, session history, knowledge base
- [x] Memory recall, emulator quirks DB, ROM compatibility notes, preference learning
- [x] MCP tools: `store_memory`, `recall_memory`, `search_memory`, `store_quirk`, `get_quirks`

### 13.3 Automated Repair & Self-Healing Framework (M63) ✅
- [x] **Engine:** `engines/self_healer.py` (550 lines) — broken symlink/orphan detection, config repair, path fixer
- [x] Pre/post-operation validation hooks, continuous integrity monitoring
- [x] MCP tools: `detect_issues`, `auto_repair`, `repair_history`, `healing_status`
- [x] `scripts/repair_runner.ps1` for PowerShell automated repair

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
- Current: **364+ core tests passing** (M1–M15 + drive_indexer)
- Additional test files for M16–M66 engines
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
