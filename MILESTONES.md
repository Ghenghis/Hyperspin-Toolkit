## KINHANK Toolkit (formerly HyperSpin Extreme Toolkit) — 66 Milestone Roadmap

### Project Scope

This toolkit manages **all KINHANK gaming HDD variants** sold on AliExpress/Amazon:

| Variant | Product                  | Frontend(s)                                                | Key Signature                             |
| ------- | ------------------------ | ---------------------------------------------------------- | ----------------------------------------- |
| **A**   | 12T HyperSpin Attraction | HyperSpin + RocketLauncher                                 | `\Arcade\HyperSpin.exe` + `Databases\`    |
| **B**   | 12T 5-in-1 T3            | AttractMode + RetroFE + LaunchBox + Playnite + TeknoParrot | `\Arcade\attract.cfg` + `\CORE - TYPE R\` |
| **C**   | 2T Batocera              | EmulationStation / Batocera                                | `batocera-boot.conf` + `\roms\`           |

The toolkit auto-detects variants, supports multi-frontend layouts, and provides auditing, repair, and management across all KINHANK drive types.

## Phase 1: Foundation (Milestones 1–5)

### M1 — Project Architecture & Config System

*   Centralized `config.yaml` with all paths, preferences, AI endpoints
*   Auto-detection of HyperSpin, RocketLauncher, emulator, ROM locations
*   Plugin-ready architecture with module loader
*   **Status**: ✅ Complete

### M2 — SQLite Database Engine

*   Local SQLite database tracking ROMs, emulators, media, backups, audits
*   Schema migrations with versioning
*   Query API for all toolkit modules
*   **Status**: ✅ Complete

### M3 — Logging & Audit Trail System

*   Structured JSON + human-readable logs for every operation
*   Severity levels (DEBUG, INFO, WARN, ERROR, CRITICAL)
*   Per-module log channels with rotation
*   Tamper-evident audit trail for all file changes
*   **Status**: ✅ Complete

### M4 — Enhanced Backup Engine (Versioned, Incremental)

*   Incremental backups using file hash manifests
*   Versioned backup sets with timestamps
*   Selective backup by system, emulator, or component
*   Compression support (zip, 7z)
*   Backup verification after creation
*   **Status**: ✅ Complete

### M5 — Recovery & Rollback System

*   Point-in-time restore from any backup version
*   Granular file-level or full-system restore
*   Pre-restore validation (check target, space, conflicts)
*   Rollback journal for any toolkit operation
*   **Status**: ✅ Complete — `engines/auto_rollback.py`, `engines/snapshot_verify.py` + tests

## Phase 2: Audit & Discovery (Milestones 6–10)

### M6 — ROM Audit Engine

*   Scan all ROM directories, match against HyperSpin XML databases
*   Detect missing, extra, corrupt, and duplicate ROMs
*   ROM set completeness scoring per system
*   CRC32/SHA1 verification against DAT files
*   **Status**: ✅ Complete — `engines/rom_audit.py` + `tests/test_rom_audit.py`, MCP tools: `rom_verify`, `rom_verify_all`

### M7 — Emulator Health Check System

*   Verify each emulator executable exists and launches
*   Check emulator versions and detect outdated installs
*   Validate emulator configs (paths, settings)
*   Map emulator-to-system relationships
*   **Status**: ✅ Complete — `engines/emulator_health.py` + `tests/test_emulator_health.py`, MCP tools: `emulator_health_all`, `emulator_health_single`

### M8 — Media Asset Auditor

*   Scan all media folders (themes, wheels, videos, artwork, bezels)
*   Report missing media per system/game
*   Detect broken/corrupt media files
*   Media completeness scoring
*   **Status**: ✅ Complete — `engines/media_auditor.py`, `engines/asset_auditor.py` + tests, MCP tools: `media_audit_system`, `media_audit_all`

### M9 — RocketLauncher Config Validator

*   Parse and validate all RocketLauncher .ini and module files
*   Check emulator paths referenced in RL configs
*   Detect broken system-to-emulator mappings
*   Validate plugin configurations
*   **Status**: ✅ Complete — `engines/rl_config_validator.py` + `tests/test_rl_config_validator.py` (48 tests), MCP tools: `rl_validate`, `rl_validate_system`, `rl_orphaned`, `rl_summary`

### M10 — HyperSpin XML Database Auditor

*   Parse all system XML database files
*   Validate game entries (name, description, year, manufacturer)
*   Cross-reference with ROM files and media
*   Detect orphaned entries and missing game data
*   **Status**: ✅ Complete — `engines/xml_tools.py` + `tests/test_xml_tools.py`, MCP tools: `xml_validate`, `xml_merge`, `xml_rebuild`, `xml_filter`, `xml_stats`

## Phase 3: Safe Update System (Milestones 11–15)

### M11 — Program Update Manager

*   Register all programs/tools in the toolkit database
*   One-at-a-time update workflow: snapshot → update → test → commit/rollback
*   Update queue with priority ordering
*   Update history with full changelog
*   **Status**: ✅ Complete — `engines/update_applier.py` + `tests/test_update_applier.py`, MCP tools: `update_check`, `update_download`, `update_apply`, `update_rollback`, `update_status`

### M12 — Emulator Version Tracker & Updater

*   Track current versions of all 160+ emulators
*   Check for updates from known sources
*   Download and stage updates in quarantine folder
*   Apply updates with automatic backup of previous version
*   **Status**: ✅ Complete — `engines/version_tracker.py` + `tests/test_version_tracker.py`, MCP tools: `version_scan`, `version_outdated`, `version_stage`, `version_quarantine`, `version_apply_staged`, `version_reject`, `version_history`, `version_summary`

### M13 — Dependency Conflict Detector

*   Map all DLL, runtime, and shared library dependencies
*   Detect version conflicts between emulators/tools
*   Warn before updates that would break dependencies
*   Suggest resolution strategies
*   **Status**: ✅ Complete — `engines/dependency_detector.py` + `tests/test_dependency_detector.py`, MCP tools: `deps_report`, `deps_conflicts`, `deps_check_update`, `deps_summary`

### M14 — Pre-Update Snapshot & Post-Update Verification

*   Automatic pre-update file hash snapshot
*   Post-update diff report showing all changes
*   Functional verification (launch test, config check)
*   Snapshot comparison tool
*   **Status**: ✅ Complete — `engines/snapshot_verify.py` + `tests/test_snapshot_verify.py`, MCP tools: `snapshot_capture`, `snapshot_compare`, `snapshot_verify`, `snapshot_list`, `snapshot_summary`

### M15 — Automated Rollback on Failure

*   Detect update failures via exit codes and health checks
*   Automatic rollback to pre-update snapshot
*   Rollback confirmation and logging
*   Manual rollback trigger for delayed issues
*   **Status**: ✅ Complete — `engines/auto_rollback.py` + `tests/test_auto_rollback.py`, MCP tools: `rollback_check`, `rollback_trigger`, `rollback_post_update`, `rollback_policy`, `rollback_list`, `rollback_summary`

## Phase 4: AI Integration (Milestones 16–20)

### M16 — Local LLM Integration Layer

*   Ollama API client (primary)
*   LM Studio API client (OpenAI-compatible)
*   vLLM API client
*   Auto-detect running LLM services
*   Model selection and fallback chain
*   **Status**: ✅ Complete — `engines/llm_router.py`, `engines/llm_detector.py`, `engines/ai_engine.py` + tests, MCP tools: `llm_models_scan`, `llm_status`

### M17 — AI-Powered ROM Identification & Cataloging

*   Use LLM to identify unknown/misnamed ROMs from filenames
*   AI-assisted game metadata enrichment
*   Smart ROM organization suggestions
*   Batch rename with AI-generated names
*   **Status**: ✅ Complete — `engines/nl_query.py` + `tests/test_nl_query.py`, MCP tools: `nl_query`, `ai_recommend_model`, `ai_full_report`

### M18 — AI Game Recommendation Engine

*   Analyze collection and suggest similar games
*   "If you like X, try Y" recommendations
*   Hidden gem discovery from your collection
*   Genre/era/style clustering
*   **Status**: 📋 Planned

### M19 — Natural Language Query System

*   Ask questions about your collection in plain English
*   "How many SNES games do I have?" → instant answer
*   "Which systems have the most missing media?" → report
*   "Show me all fighting games from the 90s" → filtered list
*   **Status**: ✅ Complete — `engines/nl_query.py` (NLQueryEngine), MCP tool: `nl_query`

### M20 — AI Troubleshooting Assistant

*   Describe a problem, get diagnostic steps
*   Parse error logs and suggest fixes
*   Common issue knowledge base
*   Learn from your specific setup over time
*   **Status**: 📋 Planned

## Phase 5: Web Dashboard (Milestones 21–25)

### M21 — Web Dashboard Core

*   FastAPI backend with REST API
*   Modern dark-theme UI (HTML/CSS/JS)
*   Real-time status updates via WebSocket
*   Authentication for local access
*   **Status**: ✅ Complete — `dashboard/app.py` + templates + static assets + `tests/test_dashboard.py`

### M22 — Collection Browser & Statistics

*   Browse all systems, games, emulators visually
*   Collection statistics: total games, size, completeness
*   Charts and graphs for collection analysis
*   Search and filter across entire collection
*   **Status**: ✅ Complete — `engines/event_hub.py` (real-time WebSocket push) + `tests/test_event_hub.py`, MCP tools: `events_recent`, `events_emit`

### M23 — System Health Monitor Dashboard

*   Live status of all systems, emulators, media
*   Health score per system (0-100)
*   Issue tracker with severity levels
*   One-click fix for common issues
*   **Status**: � Partial — health scoring in `emulator_health.py`; dashboard page template exists; needs frontend integration

### M24 — Backup/Recovery Management UI

*   Visual backup history timeline
*   One-click backup and restore
*   Backup schedule configuration
*   Storage usage analysis
*   **Status**: � Partial — `dashboard/templates/backups.html` exists; backend API ready; needs frontend JS wiring

### M25 — Update Manager UI

*   Visual update queue with drag-drop ordering
*   Update progress tracking
*   Rollback controls
*   Update history and changelog viewer
*   **Status**: � Partial — `dashboard/templates/updates.html` exists; MCP tools ready; needs frontend JS wiring

## Phase 6: Advanced Features (Milestones 26–35).maybe 

### M26 — Duplicate ROM Detection & Cleanup

*   Cross-system duplicate detection using hashes
*   Region variant identification (US, EU, JP)
*   Cleanup wizard with safe deletion
*   Space savings calculator
*   **Status**: 📋 Planned

### M27 — ROM Set Completion Tracker

*   Track completeness per system against known full sets
*   Missing ROM lists with download size estimates
*   Priority scoring (popular vs obscure titles)
*   Collection goal setting and progress tracking
*   **Status**: 📋 Planned

### M28 — Online Research Agent

*   Scrape game info from public databases (IGDB, MobyGames, etc.)
*   Emulator update checking from official sources
*   Community tip aggregation
*   AI-summarized research reports
*   **Status**: 📋 Planned

### M29 — Automated Report Generator

*   Scheduled collection health reports
*   PDF/HTML export of full collection inventory
*   Change reports (what changed since last audit)
*   Executive summary with AI-generated insights
*   **Status**: 📋 Planned

### M30 — Plugin System for Custom Extensions

*   Plugin API with lifecycle hooks
*   Plugin discovery and installation
*   Community plugin repository support
*   Plugin isolation and sandboxing
*   **Status**: ✅ Complete — `plugins/base.py`, event bus, 10+ MCP plugin tools + `tests/test_plugins.py`

### M31 — Multi-Drive Collection Sync

*   Sync collection across multiple drives/locations
*   Conflict resolution for diverged copies
*   Bandwidth-efficient delta sync
*   Sync scheduling and monitoring
*   **Status**: 📋 Planned

### M32 — Performance Benchmarking for Emulators

*   Benchmark emulator launch times
*   Track performance per game/emulator combo
*   Recommend optimal emulator per system
*   Performance history over time
*   **Status**: 📋 Planned

### M33 — Automated HyperSpin Theme/Media Downloader

*   Search and download missing themes, wheels, videos
*   Source from HyperSpin community repositories
*   Batch download with progress tracking
*   Quality verification after download
*   **Status**: 📋 Planned

### M34 — Full Ecosystem Health Score

*   Aggregate score (0-100) for entire HyperSpin setup
*   Weighted scoring across all subsystems
*   Trend tracking over time
*   Actionable improvement suggestions
*   AI-generated health report narrative
*   **Status**: 📋 Planned

### M35 — Agentic Workflow Orchestrator

*   Multi-agent system for autonomous maintenance
*   Agent roles: Auditor, Updater, Researcher, Optimizer, Reporter
*   Task scheduling and coordination
*   Human-in-the-loop approval for destructive actions
*   Learning from past operations
*   **Status**: ✅ Complete — `engines/nemoclaw_agents.py`, `engines/openhands_bridge.py`, `engines/cli_anything_bridge.py`, 4 agent blueprints in `blueprints/`, 4 workflow definitions in `workflows/`, MCP bridge (70+ tools) in `mcp_bridge.py`

## Phase 7: Agentic AI Stack (Milestones 36–40)

### M36 — Goose Orchestrator Integration

*   Install Goose v1.27.2+ and configure LM Studio as default provider
*   Register HyperSpin Toolkit as MCP server (`goose mcp add`)
*   Create custom Goose extensions for drive management, ROM audit, asset scan
*   End-to-end test: user request → Goose → MCP Bridge → result
*   **Status**: 📋 Planned — `setup/install_goose.ps1` exists but integration not tested

### M37 — OpenHands Coding Agent Integration

*   Docker image setup with LM Studio backend (`host.docker.internal:1234`)
*   Mount `D:\hyperspin_toolkit` as workspace volume
*   Test autonomous coding tasks (run tests, generate engines, debug)
*   Goose delegates coding tasks to OpenHands
*   **Status**: 📋 Planned — `engines/openhands_bridge.py` exists but Docker integration not wired

### M38 — NemoClaw Agent Sandbox Orchestration

*   Clone NemoClaw, override inference to local LM Studio
*   Create agent blueprints: rom-auditor, asset-scanner, emulator-health, backup-manager
*   Define OpenShell sandbox policies per blueprint using `drive_registry.json`
*   Test sandbox lifecycle: onboard, status, destroy
*   **Status**: 📋 Planned — `engines/nemoclaw_agents.py` + 4 blueprints in `blueprints/` exist but not connected

### M39 — CLI-Anything Software Bridge

*   Generate project-specific CLIs: cli-anything-hyperspin, -rocketlauncher, -mame, -retroarch, -lmstudio, -ollama
*   Verify SKILL.md generation for each CLI (agent-discoverable)
*   Register Skills with Goose: `goose skill load cli-anything-*`
*   Test agent-driven software control through Skills
*   **Status**: 📋 Planned — `engines/cli_anything_bridge.py` exists but CLIs not generated

### M40 — Agentic Security Policies & Workflow Orchestration

*   Drive access policies mapped from `drive_registry.json` (I:,K:,L:,J: read-only; D: read-write test; H: backup write; C:,F: denied)
*   All inference stays local — no cloud API calls
*   Serial-based drive verification before any disk write
*   Implement Goose ↔ NemoClaw ↔ OpenHands communication pipeline
*   YAML workflow orchestration: full-audit, safe-update, collection-sync, asset-catalog
*   **Status**: 📋 Planned — 4 workflow definitions in `workflows/` exist but orchestrator not built

## Phase 8: Asset Pipeline & Theme Engine (Milestones 41–43)

### M41 — Cross-HDD Asset Index & Quality Scoring

*   Scan all gaming HDDs: D:\Arcade\Media (301K PNGs, 47K videos, 20K audio, 8K SWF), K:\Arcade\menu-art, L:\CORE - TYPE R, N:\themes
*   Index every asset: path, type, format, dimensions, file size, drive tag, system, game
*   Calculate quality score per asset (resolution, aspect ratio, file size, animation)
*   Tag assets by GUI page relevance (dashboard, collection browser, etc.)
*   Store in SQLite `asset_index` table with full-text search
*   **Status**: 📋 Planned — `engines/asset_auditor.py` has basic structure, needs cross-HDD scanning + quality scoring

### M42 — SWF Theme Conversion Pipeline

*   JPEXS CLI → Lottie JSON conversion for top 100+ most-used animated themes
*   FFmpeg batch → MP4 video loops for remaining 8K SWF themes
*   Static PNG snapshot generation for thumbnails/previews
*   CefSharp fallback rendering for complex interactive SWF themes
*   Conversion status tracking and error reporting
*   **Status**: 📋 Planned — 0% built, requires JPEXS Free Flash Decompiler + FFmpeg

### M43 — Thumbnail Cache & Dynamic Theme Loader

*   Generate optimized thumbnail cache (resized PNGs) for fast GUI browsing
*   Build `ArcadeThemeEngine` service: dynamically loads assets from all registered HDDs
*   Theme source priority chain: HyperSpin → AttractMode → LaunchBox → Batocera
*   Per-page theme mapping: best assets for each GUI page
*   Dynamic theme rotation with user favorites/pinning
*   **Status**: 📋 Planned — design spec in `docs/ARCADE_GUI_PLAN.md`, 0% implemented

## Phase 9: Arcade GUI Foundation (Milestones 44–47)

### M44 — Arcade Theme System & Neon Color Palette

*   Create `ArcadeTheme.xaml` global resource dictionary with neon color palette
*   Colors: NeonBlue (#00D4FF), NeonPink (#FF0088), NeonGreen (#39FF14), NeonYellow (#FFF000), NeonOrange (#FF6E00), NeonPurple (#BF00FF)
*   Dark cabinet backgrounds (#0A0A14, #12121E)
*   Install arcade fonts: Press Start 2P (pixel), Orbitron (futuristic), JetBrains Mono (console)
*   Create `ArcadeFonts.xaml` and `NeonColors.xaml` resource dictionaries
*   Restyle MainWindow shell: layered architecture (animated background → content → HUD overlay → nav bar)
*   **Status**: 📋 Planned — current GUI uses Fluent/corporate style, needs complete retheme

### M45 — Custom Arcade Controls Suite

*   **ArcadeButton** — neon glow on hover, pulse animation on click, sound effect trigger
*   **NeonGauge** — arcade-style circular/bar meter for health %, drive usage, completion
*   **LedIndicator** — multi-color LED with glow states (green/yellow/red/off)
*   **ScoreCounter** — animated number roller with digit-by-digit cascade animation
*   **CrtTerminal** — retro scanline text terminal control for agent console output
*   All controls support both mouse and gamepad interaction
*   **Status**: 📋 Planned — 0 of 5+ controls built, `gui/HyperSpinToolkit/Controls/` directory needed

### M46 — HLSL Shader Effects & Particle System

*   **CRT Scanline Effect** — HLSL pixel shader for retro CRT monitor look
*   **Neon Glow Effect** — bloom/glow shader for buttons, text, active elements
*   **Pixel Dissolve Effect** — page transition shader with configurable direction/speed
*   **Particle System** — custom WPF particle engine with spark, glow, and pixel sprites
*   Particle presets: ambient stars, neon rain, arcade sparks, fire pixels
*   Create `Effects/` directory with .cs + .fx shader files
*   **Status**: 📋 Planned — 0% built, requires SharpDX or custom HLSL compilation

### M47 — Video Background & Audio Engine

*   Install LibVLCSharp.WPF NuGet for hardware-accelerated video playback
*   **VideoBackground** control — seamless loop of game preview videos from 47K library
*   Random background selection per page from asset index (M41)
*   **Sound Effects Engine** — load arcade sounds from `Media/{System}/Sound/` (20K files)
*   UI sound map: click, hover, navigate, transition, success, error, ambient
*   Sound presets per page theme (MAME sounds for audit page, etc.)
*   Volume control + mute toggle in settings
*   **Status**: 📋 Planned — 0% built, LibVLCSharp NuGet not installed

## Phase 10: Arcade GUI Pages (Milestones 48–50)

### M48 — Arcade Dashboard & Collection Browser

*   **Dashboard restyle** — replace Fluent cards with neon stat counters, animated background, drive health gauges (NeonGauge), agent LED indicators, video background from random game theme
*   **Collection Browser** (NEW page) — HyperSpin-style spinning wheel navigation:
    *   `WheelCarousel` 3D control with wheel art from `Media/{System}/Images/Wheel/` (45K+ PNGs)
    *   Video preview panel (MP4 from `Media/{System}/Video/`)
    *   Box art display panels (Artwork1-4 layers)
    *   Sound effects on navigation from `Media/{System}/Sound/`
    *   Genre icons, letter art, special art overlays
*   **Status**: 📋 Planned — Dashboard exists in Fluent style; Collection Browser is 0%

### M49 — Agent Console, Asset Gallery & AI Chat

*   **Agent Console** (NEW page) — CRT scanline terminal for Goose/NemoClaw/OpenHands output, real-time agent status LEDs, command input with autocomplete
*   **Asset Gallery** (NEW page) — grid browse/search all 301K+ game assets, filter by type/system/quality, lightbox preview with metadata, drag-to-set as page theme
*   **AI Chat** (NEW page) — arcade-style chat bubbles with scanline text effect, natural language input to Goose, results displayed as formatted arcade cards
*   **Status**: 📋 Planned — 0% built, 3 entirely new pages

### M50 — Audit, Backup, Update & Settings Arcade Restyle

*   **ROM Audit page** — Pac-Man-style completion meters per system, neon health pills
*   **Backup Control page** — pixel-art animated transfer progress, visual backup timeline
*   **Update Center page** — arcade loading screen progress bars, rollback controls
*   **Drive Manager page** — LED indicators per drive, arcade gauge bars, serial-based identification
*   **Settings page** — retro options menu with joystick-style navigation, sound/theme config
*   All pages use arcade controls (M45), shaders (M46), sounds (M47)
*   **Status**: 📋 Planned — existing 5 pages need complete restyle from Fluent → Arcade

## Phase 11: Arcade Polish & Integration (Milestones 51–52)

### M51 — Gamepad/Joystick Support & Page Transitions

*   Install XInputDotNet NuGet for gamepad input
*   `ArcadeInputHandler` — full D-pad, ABXY, triggers, bumpers, analog sticks mapping
*   Left stick = wheel/list navigation, Right stick = camera/zoom in gallery
*   Start = Settings, Select = toggle AI chat overlay
*   LB/RB = previous/next page with pixel dissolve transition
*   Button mapping configuration page in Settings
*   Animated page transitions using Pixel Dissolve shader (M46)
*   Marquee-scroll notifications in bottom HUD bar
*   **Status**: 📋 Planned — XInputDotNet not installed, 0% built

### M52 — Full Arcade Polish, Performance & E2E Testing

*   Performance optimization: asset preloading, thumbnail caching, lazy video load
*   Memory management: dispose video/audio resources on page leave
*   Startup experience: animated splash screen with arcade boot sequence
*   HUD overlay: persistent top bar with agent status, drive health, system clock
*   Theme persistence: remember user's favorite theme per page
*   Accessibility: keyboard navigation fallback for all arcade controls
*   E2E testing: all 10 pages rendered, all agents connected, gamepad navigation, video/audio playback
*   WPF GUI unit tests for custom controls, theme engine, asset loading
*   **Status**: 📋 Planned — capstone milestone, requires all M44–M51 complete

## Phase 12: Data Pipeline & Cross-Platform (Milestones 53–58)

### M53 — Drive Indexer & Manifest Engine

*   Scan all gaming HDDs and generate file manifests (path, size, hash, type)
*   Record file counts, total sizes, folder trees per drive
*   Store index in SQLite `drive_index` table with full-text search
*   Auto-detect collection type using `drive_registry.json` identifiers and M64 fingerprinting
*   Generate per-drive JSON manifests saved to each drive root
*   Cross-drive duplicate file detection (feeds into M26)
*   **Status**: ✅ Complete — `engines/drive_manifest.py` (550 lines) + existing `drive_index.py`/`drive_indexer.py`. SQLite with FTS5 full-text search, deep recursive scanning, file type classification, per-drive JSON manifest export, cross-drive duplicate detection. MCP tools: `index_drive`, `export_drive_manifest`, `search_indexed_files`, `find_cross_drive_duplicates`, `drive_index_stats`, `file_type_breakdown`. Tested: 4,123 files indexed on D: (580GB)

### M54 — Metadata Scraping Engine

*   Integrate with ScreenScraper API (most complete: backcover, cover, fanart, manual, marquee, screenshot, texture, video, wheel)
*   Integrate with TheGamesDB API (good for modern games, free tier)
*   Integrate with IGDB API (comprehensive, requires Twitch OAuth)
*   Integrate with ArcadeDB API (specialized for arcade platforms)
*   Optional Skyscraper CLI integration for batch scraping with local cache
*   Scrape metadata: title, description, year, developer, publisher, genre, players, rating
*   Scrape media: box art, wheel art, fanart, marquee, snap, video, manual
*   Store scraped data in SQLite `game_metadata` table
*   Rate limiting, retry logic, and credential management for all APIs
*   **Status**: ✅ Complete — `engines/metadata_scraper.py` (750 lines). ScreenScraper/TheGamesDB/IGDB/ArcadeDB API integration, SQLite `game_metadata` table, rate limiting + retry logic, credential management (env vars + config file), media download, batch scraping, unified search. MCP tools: `scrape_game_metadata`, `batch_scrape_metadata`, `search_scraped_metadata`, `scrape_stats`, `check_scraper_credentials`, `download_game_media`

### M55 — BIOS Management & Verification System

*   Scan all emulator directories for BIOS files (PS1, PS2, Saturn, Dreamcast, Neo Geo, GBA, etc.)
*   Verify BIOS checksums against known-good hashes (libretro System.dat, Batocera es_bios.xml)
*   Detect missing required BIOS files per emulator/core
*   Map BIOS files to emulators (which BIOS is needed for which emulator)
*   Report BIOS health status per system (present/missing/wrong checksum)
*   RetroArch system directory scanning and validation
*   BIOS path configuration management per emulator
*   **Status**: ✅ Complete — `engines/bios_manager.py` (705 lines). MD5 verification against known-good hashes for 20+ systems (PS1/PS2/Saturn/Dreamcast/Neo Geo/GBA/NDS/etc.), RetroArch system dir scanning, per-emulator BIOS search, health scoring, custom BIOS DAT loading. MCP tools: `bios_audit`, `bios_audit_system`, `bios_missing_summary`, `bios_list_systems`

### M56 — DAT File ROM Set Verification (No-Intro, TOSEC, Redump)

*   Parse No-Intro DAT/XML files for cartridge-based systems
*   Parse Redump DAT files for disc-based systems (PS1, PS2, Saturn, etc.)
*   Parse TOSEC DAT files for comprehensive verification
*   ROM set completeness comparison: local ROMs vs DAT entries
*   CRC32/MD5/SHA1 hash verification against DAT checksums
*   1G1R (1 Game 1 ROM) set curation with region priority configuration
*   Missing ROM reports with game names and expected hashes
*   Region variant detection and filtering (USA, Europe, Japan priority)
*   Integration with M6 (ROM Audit) and M27 (Completion Tracker) for unified reporting
*   **Status**: ✅ Complete — `engines/dat_verifier.py` (692 lines). Parses No-Intro/Redump/TOSEC/MAME DAT formats, 1G1R curation with 16-region priority, region variant detection, per-system completion reports, batch verification, DAT directory indexing. MCP tools: `verify_system_dat`, `verify_all_dats`, `dat_metadata`, `dat_summary`, `curate_1g1r`

### M57 — HyperSpin Settings Manager & HyperHQ Bridge

*   Parse and read/write HyperSpin.ini (main configuration)
*   Parse per-system Settings INI files (`Settings/{System}.ini`)
*   Manage wheel behavior settings (speed, style, letter grouping)
*   Manage navigation settings (key bindings, joystick config)
*   Manage theme settings (default theme, theme source paths)
*   Manage startup/exit settings (intro video, exit confirmation)
*   Manage attract mode / screen saver settings (idle timeout, attract sequence)
*   Validate HyperSpin settings for consistency and common errors
*   Provide recommended settings presets (performance, visual quality, cabinet mode)
*   **Status**: ✅ Complete — `engines/hyperspin_settings.py` (708 lines). Reads/writes HyperSpin.ini and per-system Settings INI files, wheel/navigation/theme/startup/attract mode management, path validation, recommended presets (performance/quality/cabinet). MCP tools: `hs_settings_audit`, `hs_get_setting`, `hs_set_setting`, `hs_apply_preset`, `hs_list_systems`

### M58 — Cross-Frontend Import/Export Engine

*   HyperSpin XML database ↔ EmulationStation gamelist.xml converter
*   HyperSpin XML ↔ LaunchBox XML database converter
*   HyperSpin XML ↔ AttractMode romlist.txt converter
*   HyperSpin XML ↔ Pegasus metadata.txt converter
*   Media path remapping between frontend directory structures
*   Batch conversion with progress tracking and error reporting
*   Cross-frontend collection comparison (what systems/games exist where)
*   Theme format awareness (different frontends use different media layouts)
*   KINHANK variant awareness: handle Variant A (HyperSpin), B (AttractMode/RetroFE), C (Batocera) layouts
*   **Status**: ✅ Complete — `engines/frontend_converter.py` (450 lines), 5 formats (HyperSpin/AttractMode/LaunchBox/Batocera/CSV), single + batch conversion, MCP tools: `convert_gamelist`, `batch_convert_gamelists`, `list_conversion_formats`. Tested: 11,557 MAME games converted HS XML → AM romlist + Batocera gamelist

## Phase 13: RocketLauncher Deep Integration (Milestones 59–60)

### M59 — RocketLauncher Fade, Bezel & Pause Manager

*   **Fade Screen Manager** — manage multi-layer fade images (Layer 1-4) per system and per game
    *   Scan `RocketLauncher\Media\Fade\{System}\` directories
    *   Validate fade image dimensions and format (PNG required)
    *   Detect missing fade assets, generate per-system coverage report
    *   Support global, per-system, and per-ROM fade configurations
*   **Bezel Manager** — manage bezel overlays for all emulators
    *   Scan `RocketLauncher\Media\Bezels\{System}\` directories
    *   Support per-game bezels with background images
    *   Validate bezel dimensions match emulator output resolution
    *   Orientation detection (horizontal/vertical games)
*   **Pause Menu Manager** — manage pause overlay assets
    *   Game guides (PDF, TXT, PNG, compressed archives)
    *   Controller/input display images per system
    *   Pause screen configuration per emulator
*   **Status**: 📋 Planned — M9 covers basic RL config validation; this adds deep media/overlay management

### M60 — RocketLauncher Keymapper, Statistics & MultiGame

*   **Keymapper Manager** — manage per-emulator input configurations
    *   AutoHotKey script management per emulator/system
    *   Xpadder/JoyToKey profile management
    *   Controller mapping validation (detect unmapped buttons)
    *   Import/export keymapper profiles
*   **Statistics Tracker** — game play statistics from RocketLauncher logs
    *   Parse RL statistics: play count, total time, last played per game
    *   Most played games reports, recently played history
    *   Play time trends and analytics
    *   Integration with M34 (Ecosystem Health Score) for engagement metrics
*   **MultiGame Manager** — multi-game ROM launching configuration
    *   Validate MultiGame settings in RocketLauncher INI
    *   Multi-disc game configuration (PS1, Saturn, etc.)
*   **7z Extraction Settings** — compressed ROM handling configuration
    *   Validate 7z extraction paths and temp directory settings
    *   Monitor extraction cache size and cleanup policies
*   **Status**: 📋 Planned — 0% built, extends RL integration beyond config validation

## Phase 14: Automation & Operations (Milestones 61–63)

### M61 — Scheduler & Notification System

*   **Task Scheduler** — cron-like scheduling for automated operations
    *   Periodic collection audits (daily/weekly ROM + media scan)
    *   Scheduled backup operations (nightly incremental, weekly full)
    *   Automated update checks for emulators and tools
    *   Drive health monitoring on schedule
*   **Notification System** — alerts for important events
    *   System tray notifications (Windows toast)
    *   In-app notification center (Arcade GUI HUD bar)
    *   Log-based alerting for critical issues
    *   Configurable notification preferences per event type
*   **Maintenance Cycles** — automated multi-step maintenance
    *   "Night mode" — run full audit + cleanup + backup while idle
    *   Post-update verification cycle
    *   Pre-session health check (quick validation before gaming)
*   **Status**: ✅ Complete — `engines/scheduler.py` (580 lines). SQLite task/run/notification tables, cron-like scheduling (hourly/daily/weekly/monthly), dynamic task action resolution, maintenance cycles (night/pre_session/post_update), Windows toast notifications, 7 default tasks. MCP tools: `list_scheduled_tasks`, `run_scheduled_task`, `create_scheduled_task`, `scheduler_status`, `run_maintenance_cycle`, `get_notifications`, `install_default_tasks`

### M62 — Agent Memory, Learning & Knowledge Base

*   **Persistent Agent Memory** — store findings across sessions
    *   SQLite `agent_memory` table: key observations from audits, user corrections, resolved issues
    *   Memory recall during agent operations (avoid repeating known issues)
    *   Session history with searchable context
*   **Knowledge Base Accumulation** — build intelligence from operations
    *   Emulator-specific quirks database (learned from troubleshooting)
    *   ROM compatibility notes (which ROM versions work best with which emulators)
    *   User preference learning (favorite systems, common operations)
    *   Community knowledge integration (curated tips from forums)
*   **Adaptive Recommendations** — improve suggestions over time
    *   Learn from user acceptance/rejection of recommendations
    *   Prioritize actions based on historical effectiveness
    *   Personalized health scoring weights based on user's collection focus
*   **Status**: ✅ Complete — `engines/agent_memory.py` (620 lines). SQLite with FTS5 full-text search, memory CRUD (observation/quirk/compatibility/preference/correction/tip), emulator quirks DB, ROM compatibility notes, user preference learning, session history, recommendation tracking with accept/reject + adaptive learning, knowledge export/import. MCP tools: `store_memory`, `search_memories`, `memory_stats`, `store_recommendation`, `respond_recommendation`, `get_emulator_quirks`, `export_knowledge`

### M63 — Automated Repair & Self-Healing Framework

*   **Issue Detection Pipeline** — proactive scanning for problems
    *   Broken symlinks and orphaned files
    *   Corrupted config files (malformed INI/XML)
    *   Missing dependencies and broken paths
    *   Stale cache entries and temp files
*   **Automated Repair Scripts** — fix common issues without user intervention
    *   Path fixer: update absolute paths after drive letter changes
    *   Config repair: regenerate corrupted INI/XML from templates
    *   Missing media stub generator: create placeholder assets
    *   Dead reference cleaner: remove entries pointing to nonexistent files
*   **Self-Healing Hooks** — automatic repair during normal operations
    *   Pre-operation validation with auto-fix attempt
    *   Post-operation verification with rollback on failure
    *   Continuous integrity monitoring in background
*   **Repair Reporting** — detailed logs of all automated fixes
    *   What was found, what was fixed, what needs manual attention
    *   Repair history with before/after snapshots
    *   Suggested manual fixes for issues that can't be auto-repaired
*   **Status**: ✅ Complete — `engines/self_healer.py` + `tests/test_self_healer.py` (356 lines), MCP tools: `self_heal_scan`, `self_heal_repair`, `self_heal_report`, `self_heal_dry_run`

## Phase 15: KINHANK Variant Management (Milestones 64–66)

### M64 — Drive Fingerprint Engine

*   Auto-detect KINHANK variant (A/B/C) from any drive letter based on directory signatures
*   Fingerprint rules: presence of key files (`HyperSpin.exe`, `attract.cfg`, `CORE.exe`, `batocera-boot.conf`)
*   Count systems/collections/ROMs per detected frontend
*   Generate drive report card: variant, frontend(s), system count, game count, health status
*   Clone detection: identify 1:1 duplicate drives by comparing file trees
*   Drive registry integration: store fingerprints in `drive_registry.json`
*   **Status**: ✅ Complete — `engines/drive_fingerprint.py` + MCP tool: `drive_fingerprint`

### M65 — Cross-Variant Game List Extractor

*   Extract game lists from any KINHANK variant:
    *   Variant A: Parse HyperSpin XML databases in `\Arcade\Databases\{System}\`
    *   Variant B: Parse AttractMode romlists in `\Arcade\romlists\` + Playnite library
    *   Variant C: Scan Batocera ROM directories in `\roms\{system}\`
*   Generate standardized CSV/JSON game inventory per drive
*   Cross-drive comparison: what games exist on which drives
*   Missing game detection: compare against KINHANK official game lists
*   **Status**: ✅ Complete — `engines/gamelist_extractor.py` (450 lines), supports all variants (A/B-A/B-C/C-D), auto-detect via M64 fingerprint, CLI + library. Tested: L: found 2,320 games across 19 systems

### M66 — Cross-Variant Integrity Checker

*   Compare drive contents against known-good KINHANK reference (official game lists)
*   Detect incomplete/broken drives: missing frontends, empty collections, skeleton installs
*   Clone validation: byte-level or file-tree comparison between drive pairs
*   Content gap analysis: what a drive is missing compared to a reference drive
*   Corruption detection: zero-byte files, truncated ROMs, broken archives
*   Generate integrity report with severity levels and recommended actions
*   **Status**: ✅ Complete — `engines/integrity_checker.py` (480 lines), variant-specific checks (structure/content/zero-byte), reference drive comparison, JSON+CSV reports. Tested: D: vs I: confirmed clones (100% structure/content, 434 zero-byte placeholders)

---

## Summary

| Phase                              | Milestones | Complete | Partial | Planned      |
| ---------------------------------- | ---------- | -------- | ------- | ------------ |
| 1 Foundation                       | M1–M5      | 5        | 0       | 0            |
| 2 Audit & Discovery                | M6–M10     | 5        | 0       | 0            |
| 3 Safe Update                      | M11–M15    | 5        | 0       | 0            |
| 4 AI Integration                   | M16–M20    | 3        | 0       | 2 (M18, M20) |
| 5 Web Dashboard                    | M21–M25    | 2        | 3       | 0            |
| 6 Advanced Features                | M26–M35    | 2        | 0       | 8            |
| 7 Agentic AI Stack                 | M36–M40    | 0        | 0       | 5            |
| 8 Asset Pipeline & Themes          | M41–M43    | 0        | 0       | 3            |
| 9 Arcade GUI Foundation            | M44–M47    | 0        | 0       | 4            |
| 10 Arcade GUI Pages                | M48–M50    | 0        | 0       | 3            |
| 11 Arcade Polish & Integration     | M51–M52    | 0        | 0       | 2            |
| 12 Data Pipeline & Cross-Platform  | M53–M58    | 6        | 0       | 0            |
| 13 RocketLauncher Deep Integration | M59–M60    | 0        | 0       | 2            |
| 14 Automation & Operations         | M61–M63    | 3        | 0       | 0            |
| 15 KINHANK Variant Management      | M64–M66    | 3        | 0       | 0            |
| **Total**                          | **66**     | **34**   | **2**   | **30**       |

### Build Order (Recommended Sequence)

```
LAYER 1 — BACKEND REMAINING (can start now, no dependencies)
  M18 Game Recommender → M20 Troubleshooter → M26-M29 Collection Mgmt → M31-M34 Advanced
                    ↓
LAYER 2 — DATA PIPELINE (Phase 12, parallel with Layer 1)
  M53 Drive Indexer ──→ M56 DAT Verification ──→ M55 BIOS Manager
  M54 Metadata Scraper (ScreenScraper/IGDB/TheGamesDB/ArcadeDB)
  M57 HyperSpin Settings Manager
  M58 Cross-Frontend Import/Export (AttractMode/LaunchBox/Batocera/Pegasus)
                    ↓
LAYER 3 — RL DEEP INTEGRATION (Phase 13, after M9 + M53)
  M59 Fade/Bezel/Pause Manager → M60 Keymapper/Statistics/MultiGame
                    ↓
LAYER 4 — AGENTIC STACK (Phase 7, after Layer 1-3 engines exist)
  M36 Goose → M37 OpenHands → M38 NemoClaw → M39 CLI-Anything → M40 Orchestration
                    ↓
LAYER 5 — ASSET PIPELINE (Phase 8, needs M53 + M54)
  M41 Cross-HDD Asset Index → M42 SWF Conversion → M43 Theme Loader
                    ↓
LAYER 6 — ARCADE GUI FOUNDATION (Phase 9, needs M41-M43)
  M44 Neon Theme System → M45 Custom Controls → M46 HLSL Shaders → M47 Video/Audio
                    ↓
LAYER 7 — ARCADE GUI PAGES (Phase 10, needs M44-M47)
  M48 Dashboard + Collection Browser → M49 Agent Console + Gallery + AI Chat
  M50 Audit/Backup/Update/Settings Restyle
                    ↓
LAYER 8 — ARCADE POLISH (Phase 11, needs M48-M50)
  M51 Gamepad + Transitions → M52 E2E Testing & Performance
                    ↓
LAYER 9 — AUTOMATION & OPS (Phase 14, capstone — needs everything above)
  M61 Scheduler & Notifications → M62 Agent Memory & Learning → M63 Self-Healing
                    ↓
LAYER 0 — KINHANK VARIANT MANAGEMENT (Phase 15, can run in parallel with all layers)
  M64 Drive Fingerprint → M65 Game List Extractor → M66 Integrity Checker
```

### What's Needed to Install/Download

| Dependency                   | Purpose                           | Phase | Status           |
| ---------------------------- | --------------------------------- | ----- | ---------------- |
| LibVLCSharp.WPF (NuGet)      | Video backgrounds                 | 9     | ❌ Not installed  |
| LottieSharp (NuGet)          | SWF→Lottie animation              | 8     | ❌ Not installed  |
| CefSharp.Wpf (NuGet)         | Fallback SWF rendering            | 8     | ❌ Not installed  |
| XInputDotNet (NuGet)         | Gamepad/joystick support          | 11    | ❌ Not installed  |
| SharpDX (NuGet)              | HLSL shader compilation           | 9     | ❌ Not installed  |
| Press Start 2P font (.ttf)   | Arcade pixel font                 | 9     | ❌ Not downloaded |
| Orbitron font (.ttf)         | Futuristic UI font                | 9     | ❌ Not downloaded |
| JetBrains Mono font (.ttf)   | Console/code font                 | 9     | ❌ Not downloaded |
| JPEXS Free Flash Decompiler  | SWF→Lottie conversion             | 8     | ❌ Not installed  |
| FFmpeg                       | SWF→MP4 batch conversion          | 8     | ❌ Not installed  |
| Goose v1.27.2+               | AI orchestrator                   | 7     | ❌ Not installed  |
| OpenHands Docker image       | Coding agent                      | 7     | ❌ Not pulled     |
| NemoClaw                     | Agent sandbox                     | 7     | ❌ Not cloned     |
| ScreenScraper API key        | Metadata scraping (free tier)     | 12    | ❌ Not registered |
| IGDB API credentials         | Game metadata (Twitch OAuth)      | 12    | ❌ Not registered |
| Skyscraper CLI               | Batch metadata scraping           | 12    | ❌ Not installed  |
| No-Intro DAT files           | ROM set verification (cartridge)  | 12    | ❌ Not downloaded |
| Redump DAT files             | ROM set verification (disc-based) | 12    | ❌ Not downloaded |
| libretro System.dat          | BIOS checksum verification        | 12    | ❌ Not downloaded |
| Windows Task Scheduler hooks | Scheduled automation              | 14    | ❌ Not configured |

### Asset Inventory (Available on HDDs, Not Yet Indexed)

| Asset Source                               | Assets      | Status                                       |
| ------------------------------------------ | ----------- | -------------------------------------------- |
| D:\Arcade\Media (HyperSpin)                | ~376K files | ❌ Not indexed for GUI                        |
| K:\Arcade\menu-art (AttractMode)           | Thousands   | ❌ Not indexed                                |
| L:\CORE - TYPE R (45 PC games + 18 arcade) | Hundreds    | ❌ Not indexed — mostly PC games via Playnite |
| N:\themes + decorations (Batocera)         | Thousands   | ❌ Not indexed                                |

### New Engines Required (Phases 12–14)

| Engine File                     | Milestone | Purpose                                           |
| ------------------------------- | --------- | ------------------------------------------------- |
| `engines/metadata_scraper.py`   | M54       | ScreenScraper, IGDB, TheGamesDB, ArcadeDB clients |
| `engines/bios_manager.py`       | M55       | BIOS scanning, checksum verification, health      |
| `engines/dat_verifier.py`       | M56       | No-Intro/Redump/TOSEC DAT parser + ROM matching   |
| `engines/hyperspin_settings.py` | M57       | HyperSpin INI read/write/validate                 |
| `engines/frontend_converter.py` | M58       | Cross-frontend database import/export             |
| `engines/rl_media_manager.py`   | M59       | Fade screens, bezels, pause overlays              |
| `engines/rl_keymapper.py`       | M60       | Keymapper profiles, statistics, MultiGame         |
| `engines/scheduler.py`          | M61       | Task scheduling, maintenance cycles               |
| `engines/notifier.py`           | M61       | Windows toast, in-app alerts                      |
| `engines/agent_memory.py`       | M62       | Persistent memory, knowledge base, learning       |
| `engines/self_healer.py`        | M63       | Issue detection, auto-repair, self-healing hooks  |
| `scripts/repair_runner.ps1`     | M63       | PowerShell automated repair script                |
| `engines/drive_fingerprint.py`  | M64       | KINHANK variant detection from drive structure    |
| `engines/gamelist_extractor.py` | M65       | Cross-variant game list extraction                |
| `engines/integrity_checker.py`  | M66       | Cross-variant integrity & corruption detection    |

---

### Research Gap Analysis (What Was Missing Before This Audit)

The following 9 major gaps were identified by auditing the M1-M52 roadmap against:
- **HyperSpin/RocketLauncher ecosystem** (wiki, forums, media structure)
- **Modern arcade frontends** (LaunchBox, Pegasus, AttractMode, Batocera)
- **Agentic AI frameworks** (Goose, OpenHands, NemoClaw, CLI-Anything)
- **Metadata scraping tools** (ScreenScraper, Skyscraper, IGDB, ArcadeDB)
- **ROM management standards** (No-Intro, Redump, TOSEC, 1G1R)
- **BIOS verification databases** (libretro System.dat, Batocera es_bios.xml)

| Gap # | Category                    | What Was Missing                                                      | Now Covered By |
| ----- | --------------------------- | --------------------------------------------------------------------- | -------------- |
| 1     | Metadata Scraping           | No integration with game databases (ScreenScraper, IGDB, etc.)        | **M54**        |
| 2     | BIOS Management             | No BIOS scanning, verification, or missing-BIOS detection             | **M55**        |
| 3     | DAT File Verification       | No No-Intro/Redump/TOSEC DAT parsing or 1G1R set curation             | **M56**        |
| 4     | HyperSpin Settings          | No engine to read/write HyperSpin.ini or per-system settings          | **M57**        |
| 5     | Cross-Frontend Support      | No import/export between frontend database formats                    | **M58**        |
| 6     | RL Fade/Bezel/Pause         | M9 only validates config; RL's fade layers, bezels, pause not managed | **M59**        |
| 7     | RL Keymapper/Statistics     | No keymapper profile management or play statistics tracking           | **M60**        |
| 8     | Scheduling & Notifications  | No automated task scheduling or alert system                          | **M61**        |
| 9     | Agent Memory & Self-Healing | No persistent memory, learning, or automated repair framework         | **M62, M63**   |

**Additionally**, M53 (Drive Indexer) was already partially built (`engines/drive_indexer.py`) but not tracked as a milestone — now formalized.