# HyperSpin Extreme Toolkit — Complete Tools & Integration Research

## Your Ecosystem Audit Summary

| Metric | Value |
|---|---|
| **D:\ Drive** | 11.1 TB used / 60 GB free / 11.2 TB total |
| **Top-level system dirs** | 184 |
| **HyperSpin databases** | 422 |
| **Media directories** | 421 |
| **Emulators** | 173 (in D:\Arcade\emulators) |
| **RocketLauncher modules** | 190+ |
| **MAME version** | 0.228 (January 2021) — **current is 0.273+** |
| **MAME old archive** | `MAME - 0.211 and previous` — **CORRUPTED DIRECTORY** |

### Critical Issues Found
1. **MAME is 50+ versions behind** (0.228 vs current 0.273+) — hundreds of new games, drivers, and bug fixes missed
2. **Corrupted directory** detected: `D:\Arcade\emulators\MAME - 0.211 and previous` — I/O error on read
3. **Only 60 GB free** on 12 TB drive — need space-efficient strategies (dedup, compression, cleanup)
4. **Multiple duplicate emulator versions**: 7+ Xenia variants, 3+ Yuzu variants, 2+ PCSX2, 2+ Dolphin, etc.
5. **Many emulators are outdated** — most last modified 2020-2021

---

## PART 1: ROM Collection Management Tools

### 1.1 ROM Managers (DAT-based verification & rebuilding)

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **Igir** | Node.js CLI | [emmercm/igir](https://github.com/emmercm/igir) | Zero-setup ROM collection manager. Sort, filter, extract, archive, patch, report. Best modern tool. | **CRITICAL** |
| **RomVault** | C# GUI | [RomVault.com](https://www.romvault.com/) | Industry-standard ROM manager. Handles MAME split/merged/non-merged sets. TorrentZip support. | **CRITICAL** |
| **ClrMamePro** | Windows GUI | [mamedev.emulab.it](https://mamedev.emulab.it/clrmamepro/) | The original ROM auditor. Gold standard for MAME set verification and rebuilding. | **HIGH** |
| **Retool** | Python CLI | [unexpectedpanda/retool](https://github.com/unexpectedpanda/retool) | DAT filter for No-Intro/Redump. Superior 1G1R filtering. Use before loading DATs into ROM manager. | **HIGH** |
| **SabreTools** | C# CLI | [SabreTools/SabreTools](https://github.com/SabreTools/SabreTools) | Advanced DAT management. Dir2DAT, DAT splitting, merging, diffing. | **HIGH** |
| **DATROMTool** | Java CLI | [andrebrait/DATROMTool](https://github.com/andrebrait/DATROMTool) | DAT filtering with Retool metadata support. 1G1R, region filtering. | MEDIUM |
| **oxyromon** | Rust CLI | [alucryd/oxyromon](https://github.com/alucryd/oxyromon) | Modern ROM organizer. Downloads No-Intro/Redump DATs automatically. 1G1R sorting. | MEDIUM |
| **Emuman** | Rust CLI | [tuffy/emuman](https://github.com/tuffy/emuman) | MAME-specific file manager. Audits ROMs against MAME listxml. | MEDIUM |
| **RomVaultX** | C# | [mnadareski/RomVaultX](https://github.com/mnadareski/RomVaultX) | Next-gen ROM collecting. Depot-style storage. | LOW |

### 1.2 MAME-Specific Tools

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **Arcade Manager** | C# GUI/CLI | [cosmo0/arcade-manager](https://github.com/cosmo0/arcade-manager) | Filter MAME/FBNeo romsets. Best-of lists. Remove unwanted games. | **HIGH** |
| **BestArcade** | Python | [Voljega/BestArcade](https://github.com/Voljega/BestArcade) | Generate curated arcade romsets from best-of lists. Neo Geo, Naomi, Model 2/3. | **HIGH** |
| **MAME Official** | C++ | [mamedev/mame](https://github.com/mamedev/mame) | Official MAME source. Use `-verifyroms` and `-listxml` for auditing. | **CRITICAL** |
| **Progetto-SNAPS** | Media packs | [progettosnaps.net](https://www.progettosnaps.net/) | Official MAME media: snapshots, titles, marquees, cabinets, manuals, icons. | **HIGH** |
| **MAME Extras** | DATs/Media | [pleasuredome.github.io](https://pleasuredome.github.io/pleasuredome/mame/) | Reference sets, split/merged/non-merged DATs, CHD sets. | HIGH |

### 1.3 DAT File Sources

| Source | URL | Coverage | Notes |
|---|---|---|---|
| **No-Intro** | [no-intro.org](https://datomatic.no-intro.org/) | Cartridge-based consoles | Gold standard for console ROM verification |
| **Redump** | [redump.org](http://redump.org/) | Disc-based systems | CD/DVD/BD verification (PS1, PS2, Saturn, Dreamcast, etc.) |
| **MAME Listxml** | Built into MAME | Arcade | `mame64 -listxml > mame.xml` |
| **TOSEC** | [tosec.org](https://www.tosec.org/) | Everything | Broadest coverage, lower priority than No-Intro |
| **Libretro DB** | [libretro/libretro-database](https://github.com/libretro/libretro-database) | All platforms | DATs, cheats, thumbnails for RetroArch |

---

## PART 2: ROM Patching & Hacking Tools

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **Flips (Floating IPS)** | C++ GUI/CLI | [Alcaro/Flips](https://github.com/Alcaro/Flips) | Best IPS/BPS patcher. Can batch-apply patches and launch emulators. | **HIGH** |
| **PyPatcherGBA** | Python CLI | [jarrowsmith123/PyPatcherGBA](https://github.com/jarrowsmith123/PyPatcherGBA) | Python IPS/UPS/BPS patcher. Easy to integrate into our toolkit. | MEDIUM |
| **rombp** | Go CLI | [blakesmith/rombp](https://github.com/blakesmith/rombp) | Lightweight IPS/BPS patcher. | LOW |
| **xdelta3** | C CLI | [xdelta.org](https://github.com/jmacd/xdelta) | Binary delta encoding. For large patches (CD/DVD games). | MEDIUM |
| **RomHacking.net** | Web tools | [romhacking.net](https://www.romhacking.net/) | Massive patch database. Translations, hacks, fixes, improvements. | HIGH |

---

## PART 3: Media Scraping & Artwork Tools

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **Skyscraper** | C++ CLI | [muldjord/skyscraper](https://github.com/muldjord/skyscraper) | Powerful game scraper. ScreenScraper, IGDB, MobyGames, OpenRetro. Caches locally. | **HIGH** |
| **Skraper** | Windows GUI | [skraper.net](https://www.skraper.net/) | ScreenScraper-based GUI scraper. Excellent for HyperSpin media. | **HIGH** |
| **Universal XML Scraper** | Windows GUI | [Universal-Rom-Tools/Universal-XML-Scraper](https://github.com/Universal-Rom-Tools/Universal-XML-Scraper/wiki) | Scrapes to HyperSpin XML format directly. Uses ScreenScraper DB. | **HIGH** |
| **Retroscraper** | Python CLI | [zayamatias/retroscraper](https://github.com/zayamatias/retroscraper) | Python metadata/media scraper. Local DB caching. | MEDIUM |
| **tiny-scraper** | Python CLI | [Julioevm/tiny-scraper](https://github.com/Julioevm/tiny-scraper) | Simple Python scraper using ScreenScraper API. | MEDIUM |
| **EmuMovies Sync** | Windows GUI | [emumovies.com](https://emumovies.com/) | Official HyperSpin/RocketLauncher media sync tool. | HIGH |
| **LaunchBox** | Windows GUI | [launchbox-app.com](https://www.launchbox-app.com/) | Scrapes metadata + media. Can export to HyperSpin format. | MEDIUM |
| **Progetto-SNAPS** | Download packs | [progettosnaps.net](https://www.progettosnaps.net/) | Complete MAME media packs (snaps, titles, cabinets, marquees). | HIGH |

---

## PART 4: Emulator Update & Version Management

### Safe Update Strategy (with only 60GB free)

**Key principle**: Our toolkit already has snapshot→update→test→rollback pipeline. These tools feed into it.

| Tool | Type | URL | Description | Priority |
|---|---|---|---|---|
| **RetroArch** | Multi-emulator | [retroarch.com](https://www.retroarch.com/) | Built-in core updater. Covers 100+ systems via libretro cores. | **CRITICAL** |
| **EmuDeck** | Installer/Updater | [github.com/dragoonDorise/EmuDeck](https://github.com/dragoonDorise/EmuDeck) | Auto-installs and updates emulators. Good reference for update logic. | MEDIUM |
| **GitHub Release APIs** | REST API | Various | Each emulator's GitHub releases can be polled for latest versions. | **HIGH** |

### Emulators with GitHub Releases (auto-updatable)

| Emulator | Your Version (est.) | GitHub | Latest Check Method |
|---|---|---|---|
| **MAME** | 0.228 (2021) | [mamedev/mame](https://github.com/mamedev/mame/releases) | `GET /repos/mamedev/mame/releases/latest` |
| **RetroArch** | Unknown | [libretro/RetroArch](https://github.com/libretro/RetroArch/releases) | GitHub API |
| **Dolphin** | ~2021 | [dolphin-emu/dolphin](https://github.com/dolphin-emu/dolphin/releases) | GitHub API |
| **PCSX2** | 1.40 (ancient) | [PCSX2/pcsx2](https://github.com/PCSX2/pcsx2/releases) | GitHub API — **now v2.x with QT UI** |
| **RPCS3** | Unknown | [RPCS3/rpcs3](https://github.com/RPCS3/rpcs3-binaries-win/releases) | GitHub API |
| **DeSmuME** | Unknown | [TASEmulators/desmume](https://github.com/TASEmulators/desmume/releases) | GitHub API |
| **PPSSPP** | Unknown | [hrydgard/ppsspp](https://github.com/hrydgard/ppsspp/releases) | GitHub API |
| **Cemu** | Unknown | [cemu-project/Cemu](https://github.com/cemu-project/Cemu/releases) | GitHub API |
| **Redream** | Unknown | [redream.io](https://redream.io/) | Website scrape |
| **Snes9x** | Unknown | [snes9xgit/snes9x](https://github.com/snes9xgit/snes9x/releases) | GitHub API |
| **VisualBoyAdvance-M** | Unknown | [visualboyadvance-m/visualboyadvance-m](https://github.com/visualboyadvance-m/visualboyadvance-m/releases) | GitHub API |
| **Stella** | Unknown | [stella-emu/stella](https://github.com/stella-emu/stella/releases) | GitHub API |
| **Mednafen** | Unknown | [mednafen.github.io](https://mednafen.github.io/) | Website check |
| **Hatari** | Unknown | [hatari/hatari](https://github.com/hatari/hatari/releases) | GitHub API |
| **FCEUX** | Unknown | [TASEmulators/fceux](https://github.com/TASEmulators/fceux/releases) | GitHub API |
| **Nestopia** | Unknown | [0ldsk00l/nestopia](https://github.com/0ldsk00l/nestopia/releases) | GitHub API |
| **Mupen64Plus** | Unknown | [mupen64plus/mupen64plus-core](https://github.com/mupen64plus/mupen64plus-core/releases) | GitHub API |
| **ScummVM** | Unknown | [scummvm/scummvm](https://github.com/scummvm/scummvm/releases) | GitHub API |
| **DOSBox-X** | Unknown | [joncampbell123/dosbox-x](https://github.com/joncampbell123/dosbox-x/releases) | GitHub API |
| **TeknoParrot** | Unknown | [teknogods/TeknoParrotUI](https://github.com/teknogods/TeknoParrotUI/releases) | GitHub API |

### MAME Upgrade Path (Critical — You're 50+ versions behind)

```
Current: MAME 0.228 (Jan 2021)
Latest:  MAME 0.273+ (2025)

Upgrade plan:
1. Snapshot current MAME dir (toolkit backup engine)
2. Download latest MAME binary from GitHub releases
3. Use ClrMamePro/RomVault to rebuild romset for new version
   - New DAT from: mame64 -listxml > mame0273.xml
   - Scan existing ROMs against new DAT
   - Report missing/changed/removed ROMs
4. Test with a few known working games
5. Commit or rollback via toolkit pipeline

WARNING: ROM set changes between MAME versions!
- Some ROMs get renamed, split, or merged
- CHDs may change format (v4→v5)
- Need corresponding DAT file for each MAME version
- ClrMamePro "rebuild" mode handles this safely
```

---

## PART 5: HyperSpin & RocketLauncher Specific Tools

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **HyperMint** | C# GUI | [horseyhorsey/HyperMint](https://github.com/horseyhorsey/HyperMint) | HyperSpin database & media organizer. Scan, audit, manage. | **HIGH** |
| **RetroDb** | C# Web | [horseyhorsey/RetroDb](https://github.com/horseyhorsey/RetroDb) | Web server built from HyperSpin/RocketLauncher game lists. | MEDIUM |
| **OpenSpin** | C++ | [justindarc/openspin](https://github.com/justindarc/openspin) | Open source drop-in HyperSpin replacement. | LOW |
| **RocketLauncherUI** | Built-in | D:\Arcade\RocketLauncher\RocketLauncherUI\ | Manage modules, settings, per-system emulator config. | **CRITICAL** |
| **HyperHQ** | Built-in | D:\Arcade\ | HyperSpin settings manager. Wheel, theme, video config. | HIGH |
| **Universal XML Scraper** | GUI | [GitHub Wiki](https://github.com/Universal-Rom-Tools/Universal-XML-Scraper/wiki) | Creates HyperSpin-format XML databases from ScreenScraper. | HIGH |

---

## PART 6: AI & Agentic System (Local LLM Stack)

### 6.1 LLM Inference Servers

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **Ollama** | Local LLM server | [ollama/ollama](https://github.com/ollama/ollama) | Easiest local LLM. Pull models, REST API. **Primary provider.** | **CRITICAL** |
| **LM Studio** | Local LLM GUI | [lmstudio.ai](https://lmstudio.ai/) | GUI model manager + OpenAI-compatible API server. | **HIGH** |
| **vLLM** | High-perf server | [vllm-project/vllm](https://github.com/vllm-project/vllm) | PagedAttention. Best throughput for batch processing. | MEDIUM |
| **Open WebUI** | Chat interface | [open-webui/open-webui](https://github.com/open-webui/open-webui) | Beautiful Ollama web UI. RAG, file uploads, tools. | HIGH |

### 6.2 Agent Frameworks (Ollama-compatible)

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **CrewAI** | Python | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | Multi-agent orchestration. Role-based agents. Works with Ollama. | **HIGH** |
| **LangChain** | Python | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | LLM application framework. Chains, agents, tools. Ollama integration. | **HIGH** |
| **LangGraph** | Python | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | Stateful multi-actor agent workflows. Graph-based orchestration. | HIGH |
| **AutoGen** | Python | [microsoft/autogen](https://github.com/microsoft/autogen) | Microsoft's multi-agent conversation framework. | MEDIUM |
| **PydanticAI** | Python | [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | Type-safe LLM agent framework. Clean, minimal. | MEDIUM |

### 6.3 Knowledge & Memory (RAG Stack)

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **ChromaDB** | Vector DB | [chroma-core/chroma](https://github.com/chroma-core/chroma) | Embedded vector database. Perfect for local RAG. | **HIGH** |
| **Ollama Embeddings** | Embedding model | Built into Ollama | `nomic-embed-text` model for vectorizing documents. | **HIGH** |
| **SQLite (existing)** | Relational DB | Already in toolkit | Structured data: systems, ROMs, emulators, audit results. | **CRITICAL** |
| **LanceDB** | Vector DB | [lancedb/lancedb](https://github.com/lancedb/lancedb) | Serverless vector DB. No separate process needed. | MEDIUM |

### 6.4 Workflow Orchestration

| Tool | Type | GitHub/URL | Description | Priority |
|---|---|---|---|---|
| **n8n** | Self-hosted | [n8n-io/n8n](https://github.com/n8n-io/n8n) | Visual workflow automation. Ollama integration. | MEDIUM |
| **n8n AI Starter Kit** | Docker template | [n8n-io/self-hosted-ai-starter-kit](https://github.com/n8n-io/self-hosted-ai-starter-kit) | Ollama + n8n + vector DB pre-configured. | MEDIUM |
| **Local AI Packaged** | Docker template | [coleam00/local-ai-packaged](https://github.com/coleam00/local-ai-packaged) | Ollama + Open WebUI + n8n + Supabase all-in-one. | MEDIUM |

### 6.5 Recommended AI Models for This Use Case

| Model | Size | Use Case | Ollama Pull |
|---|---|---|---|
| **llama3.1:8b** | 4.7 GB | General chat, analysis, troubleshooting | `ollama pull llama3.1:8b` |
| **mistral:7b** | 4.1 GB | Fast responses, good at structured output | `ollama pull mistral:7b` |
| **codellama:13b** | 7.4 GB | Code generation, script writing | `ollama pull codellama:13b` |
| **nomic-embed-text** | 274 MB | Embeddings for RAG/vector search | `ollama pull nomic-embed-text` |
| **deepseek-coder-v2:16b** | 8.9 GB | Advanced code, JSON output | `ollama pull deepseek-coder-v2:16b` |
| **phi3:medium** | 7.9 GB | Reasoning, analysis | `ollama pull phi3:medium` |

---

## PART 7: Agentic Workflows for the Toolkit

### Agent 1: Collection Auditor Agent
```
Triggers: Scheduled (weekly) or manual
Actions:
  1. Scan all system directories for new/changed/deleted files
  2. Cross-reference ROMs with DAT files (No-Intro, Redump, MAME)
  3. Check media completeness per system
  4. Generate health scores
  5. AI summarizes findings and recommends actions
Tools: Igir, scanner.py, auditor.py, AI engine
```

### Agent 2: Safe Updater Agent
```
Triggers: New emulator release detected via GitHub API
Actions:
  1. Check GitHub releases API for each tracked emulator
  2. Compare current version vs latest
  3. If update available: notify user, wait for approval
  4. Snapshot current emulator directory
  5. Download and extract new version
  6. Run health checks (exe exists, basic launch test)
  7. Commit or rollback
Tools: update_manager.py, backup.py, GitHub API, httpx
```

### Agent 3: ROM Set Manager Agent
```
Triggers: MAME version update, or manual
Actions:
  1. Generate new DAT from updated MAME (-listxml)
  2. Audit current ROM set against new DAT
  3. Report: missing, renamed, split, merged ROMs
  4. Download/rebuild changed ROMs (with user approval)
  5. Verify rebuilt set
Tools: ClrMamePro/RomVault (CLI), Igir, MAME -verifyroms
```

### Agent 4: Media Scraper Agent
```
Triggers: After audit finds missing media, or manual
Actions:
  1. Identify systems with incomplete media (wheels, videos, themes)
  2. Query ScreenScraper/EmuMovies for missing items
  3. Download and organize into correct HyperSpin Media paths
  4. Verify media file integrity
  5. Update database with new media counts
Tools: Skyscraper, ScreenScraper API, Progetto-SNAPS
```

### Agent 5: Research Agent
```
Triggers: User question, or unknown ROM found
Actions:
  1. Query local AI about ROM identification
  2. Search No-Intro/Redump databases
  3. Cross-reference with online databases
  4. Provide game info, compatibility notes, recommended emulator
Tools: AI engine, ChromaDB (RAG), No-Intro DATs
```

### Agent 6: Space Optimizer Agent
```
Triggers: Disk space below threshold (e.g., < 100 GB)
Actions:
  1. Find duplicate ROMs across systems (hash-based)
  2. Identify old/unused backups for cleanup
  3. Find oversized media files that can be compressed
  4. Detect redundant emulator versions (7 Xenia copies!)
  5. Recommend safe cleanup actions
  6. Execute with user approval
Tools: auditor.py find_duplicate_roms(), backup.py, scanner.py
```

---

## PART 8: Integration Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Dashboard (FastAPI)               │
│  Dashboard │ Systems │ Emulators │ Backups │ AI Chat    │
└──────────────────────────┬──────────────────────────────┘
                           │ REST API + WebSocket
┌──────────────────────────┴──────────────────────────────┐
│                   Agent Orchestrator                     │
│  Auditor │ Updater │ ROM Manager │ Scraper │ Research   │
└──────────────────────────┬──────────────────────────────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
┌───┴────┐          ┌──────┴──────┐        ┌──────┴──────┐
│ Engines │          │  AI Layer   │        │External Tools│
│ scanner │          │ Ollama      │        │ Igir        │
│ backup  │          │ LM Studio   │        │ ClrMamePro  │
│ updater │          │ vLLM        │        │ RomVault    │
│ auditor │          │ ChromaDB    │        │ Flips       │
└───┬────┘          └──────┬──────┘        │ Skyscraper  │
    │                      │               │ MAME CLI    │
┌───┴──────────────────────┴───────┐       └─────────────┘
│         SQLite Database          │
│ systems│roms│emulators│backups│ai│
└──────────────────────────────────┘
```

---

## PART 9: Immediate Action Plan (Given 60 GB Free)

### Phase 1: Space Recovery (URGENT)
1. Run duplicate ROM detection across all 184 systems
2. Identify the 7 Xenia copies — consolidate to latest working version
3. Audit `MAME - 0.211 and previous` (corrupted) — may need repair or removal
4. Check for duplicate Yuzu versions (3 copies) — Yuzu is discontinued anyway
5. Compress old backups with 7-zip
6. **Estimated recovery: 20-50 GB**

### Phase 2: Core Tool Installation
1. Install **Igir** (`npm install -g igir`) — zero-setup ROM manager
2. Download latest **MAME** binary (from GitHub releases)
3. Install **Flips** for ROM patching
4. Set up **Ollama** with `llama3.1:8b` model
5. Install **ChromaDB** (`pip install chromadb`)

### Phase 3: MAME Upgrade (Biggest Impact)
1. Snapshot current `D:\Arcade\emulators\MAME` via toolkit
2. Download MAME 0.273 from GitHub
3. Generate new listxml DAT
4. Use RomVault/ClrMamePro to audit current ROM set
5. Identify what needs updating
6. Apply changes, test, commit/rollback

### Phase 4: Agentic System Activation
1. Enable GitHub release checking for all 20+ tracked emulators
2. Set up scheduled audit (weekly)
3. Build RAG knowledge base from MAME docs, No-Intro info, emulator wikis
4. Connect CrewAI for multi-agent orchestration
5. Expose everything through the web dashboard

---

## PART 10: Python Packages to Add to requirements.txt

```
# Agent frameworks
crewai>=0.80.0
langchain>=0.3.0
langchain-community>=0.3.0
langchain-ollama>=0.2.0

# Vector database (RAG)
chromadb>=0.5.0

# GitHub API polling
PyGithub>=2.0

# ROM patching
python-ips>=0.1

# Additional tools
beautifulsoup4>=4.12     # Web scraping for update checks
lxml>=5.0                # XML parsing (HyperSpin databases)
py7zr>=0.21              # 7-zip support for ROM archives
rarfile>=4.1             # RAR support
tqdm>=4.66               # Progress bars for long operations
```

---

## Summary of All Discovered Tools

| Category | Count | Key Tools |
|---|---|---|
| ROM Managers | 9 | Igir, RomVault, ClrMamePro, Retool, SabreTools, oxyromon |
| MAME Tools | 5 | MAME CLI, Arcade Manager, BestArcade, Progetto-SNAPS |
| DAT Sources | 5 | No-Intro, Redump, MAME, TOSEC, Libretro DB |
| ROM Patchers | 5 | Flips, PyPatcherGBA, rombp, xdelta3, RomHacking.net |
| Media Scrapers | 8 | Skyscraper, Skraper, Universal XML Scraper, EmuMovies |
| HyperSpin Tools | 6 | HyperMint, RetroDb, OpenSpin, RocketLauncherUI, HyperHQ |
| LLM Servers | 4 | Ollama, LM Studio, vLLM, Open WebUI |
| Agent Frameworks | 5 | CrewAI, LangChain, LangGraph, AutoGen, PydanticAI |
| Vector DBs | 3 | ChromaDB, LanceDB, Ollama Embeddings |
| Workflow Tools | 3 | n8n, AI Starter Kit, Local AI Packaged |
| **Total** | **53** | |
