# HyperSpin Extreme Toolkit v2.0

Full ecosystem management for HyperSpin, RocketLauncher, ROMs, Emulators, and Media — with a fully agentic 4-system stack powered by **Goose + OpenHands + CLI-Anything + NemoClaw**, all running locally on your RTX 3090 Ti via LM Studio and Ollama.

---

## Agentic Stack (NEW)

> **Just open Goose and describe what you want.** The four agents coordinate automatically.

```
USER (plain English)
       ↓
   G O O S E  (orchestrator — LM Studio / Devstral-24B)
       ├── HyperSpin Toolkit MCP  (14 direct tools)
       ├── CLI-Anything Bridge    (NL → CLI command translation)
       ├── NemoClaw Agents        (6 specialist reasoning agents)
       └── OpenHands Bridge       (batch file ops / browser automation)
               ↓
    D:\hyperspin_toolkit\  ←→  D:\Arcade\ (12 TB collection)
```

### Install (one-time)
```powershell
.\setup\install_goose.ps1
```

### Validate the full stack
```powershell
python setup\goose_setup.py --e2e
```

### Documentation
| Doc                                                          | Purpose                                                |
| ------------------------------------------------------------ | ------------------------------------------------------ |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)                 | Full system diagram, all agent flows, data paths       |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md)                     | How to use Goose: examples, workflows, troubleshooting |
| [docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)           | All commands, MCP tools, agents — cheat sheet          |
| [AGENTIC_TOOLS_INTEGRATION.md](AGENTIC_TOOLS_INTEGRATION.md) | Integration design, NemoClaw roles, model matrix       |

### What to say to Goose

| Goal             | Say this                                    |
| ---------------- | ------------------------------------------- |
| Health check     | "Audit my HyperSpin collection"             |
| Emulator updates | "What emulator updates are available?"      |
| Free disk space  | "How much space can I safely recover?"      |
| Fix a system     | "Fix my PlayStation 2 setup"                |
| Update MAME      | "Update MAME safely"                        |
| Rebuild MAME DB  | "Rebuild my MAME HyperSpin database"        |
| Analyse media    | "Check my SNES artwork quality"             |
| Ask anything     | "Why is my Dreamcast emulator not working?" |

### Required binaries (not included — free downloads)

| Binary                | Where                                                            | Purpose          |
| --------------------- | ---------------------------------------------------------------- | ---------------- |
| **Goose v1.27.2**     | `install_goose.ps1` auto-downloads                               | Orchestrator     |
| **LM Studio**         | [lmstudio.ai](https://lmstudio.ai)                               | Local LLM server |
| **OpenHands**         | `docker pull docker.all-hands.dev/all-hands-ai/openhands:latest` | Batch file agent |
| **Ollama** (optional) | [ollama.com](https://ollama.com)                                 | Fallback LLM     |

---

## Architecture

```
D:\hyperspin_toolkit\
├── main.py                  # CLI entry point (init, audit, backup, update, ai, dashboard, agent, stats)
├── config.yaml              # Master configuration (paths, AI, backup, dashboard)
├── config.json              # Legacy config for PowerShell inventory
├── requirements.txt         # Python dependencies
├── Launch_Toolkit.bat       # Windows launcher menu
├── MILESTONES.md            # 35-milestone roadmap
│
├── core/                    # Core framework
│   ├── config.py            # YAML config loader with dot-notation access
│   ├── database.py          # SQLite database engine (12 tables)
│   └── logger.py            # Structured JSON logging + audit trail
│
├── engines/                 # Processing engines
│   ├── scanner.py           # System/emulator/ROM/media discovery
│   ├── backup.py            # Versioned incremental backup & recovery
│   ├── update_manager.py    # Safe update pipeline (snapshot→update→test→commit/rollback)
│   ├── auditor.py           # Full ecosystem audit (ROMs, emulators, media, RocketLauncher)
│   └── ai_engine.py         # AI integration (Ollama, LM Studio, vLLM) + NL query
│
├── agents/                  # AI agent system
│   └── base_agent.py        # Auditor, Backup, Updater, Researcher agents
│
├── dashboard/               # Web dashboard (FastAPI)
│   ├── app.py               # REST API + WebSocket backend
│   ├── templates/           # Jinja2 HTML templates (6 pages)
│   └── static/              # CSS + JavaScript
│
├── plugins/                 # Plugin system with auto-discovery
├── scripts/                 # Setup, repair, and utility scripts
├── tests/                   # Test suite
├── data/                    # SQLite database + quarantine
├── logs/                    # Structured logs + audit trail
│
├── HyperSpinInventory.ps1   # Legacy PowerShell inventory engine
├── HyperSpinInventory.py    # Legacy HTML dashboard generator
└── Run_HyperSpin_Toolkit.bat # Legacy launcher
```

## Quick Start

### 1. Setup
```powershell
cd D:\hyperspin_toolkit
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
.venv\Scripts\Activate.ps1
```

### 2. Initialize (discover systems + emulators)
```bash
python main.py init
```

### 3. Full Audit
```bash
python main.py audit full
```

### 4. Launch Web Dashboard
```bash
python main.py dashboard
# Opens at http://127.0.0.1:8888
```

### 5. AI Assistant (requires Ollama, LM Studio, or vLLM running)
```bash
python main.py ai status           # Check providers
python main.py ai ask "How many SNES games do I have?"
python main.py ai query "Show systems with most ROMs"
```

## CLI Commands

| Command                                                              | Description                                     |
| -------------------------------------------------------------------- | ----------------------------------------------- |
| `python main.py init`                                                | Discover systems + emulators, populate database |
| `python main.py audit full`                                          | Full ecosystem audit                            |
| `python main.py audit system "Nintendo Entertainment System"`        | Audit one system                                |
| `python main.py audit emulators`                                     | Audit all emulators                             |
| `python main.py backup create "D:\Arcade" --label daily --type full` | Create backup                                   |
| `python main.py backup list`                                         | List all backups                                |
| `python main.py backup restore <backup_dir> <target> --dry-run`      | Restore                                         |
| `python main.py update register <name> <path>`                       | Register program update                         |
| `python main.py update queue`                                        | Show pending updates                            |
| `python main.py update history`                                      | Show update history                             |
| `python main.py ai status`                                           | Check AI provider status                        |
| `python main.py ai ask "<question>"`                                 | Ask AI assistant                                |
| `python main.py ai query "<question>"`                               | Natural language DB query                       |
| `python main.py dashboard`                                           | Launch web dashboard                            |
| `python main.py agent list`                                          | List AI agents                                  |
| `python main.py agent run auditor full_audit`                        | Run agent task                                  |
| `python main.py stats`                                               | Show collection statistics                      |

## Safe Update Pipeline

Every program update follows a strict safety pipeline:
1. **Register** — add update to queue
2. **Snapshot** — automatic pre-update backup
3. **Apply** — perform the update (copy, extract, or script)
4. **Test** — verify update works (exe check, custom test command)
5. **Commit** — mark as successful
6. **Rollback** — automatic revert if anything fails

## AI Integration

Supports three local LLM providers with automatic fallback:
- **Ollama** (primary) — `http://localhost:11434`
- **LM Studio** (secondary) — `http://localhost:1234/v1`
- **vLLM** (tertiary) — `http://localhost:8000/v1`

### AI Features
- Natural language queries about your collection
- ROM identification from filenames
- Collection health analysis with recommendations
- Troubleshooting assistant
- Conversation memory stored in SQLite

## Backup & Recovery

- **Full backups** — complete directory archive with hash manifest
- **Incremental backups** — only changed files (based on hash diff)
- **Snapshots** — lightweight pre-update backups
- **Verification** — automatic post-backup integrity check
- **Point-in-time restore** — restore any backup to any target
- **Rollback** — revert any operation from its snapshot

## Ecosystem Audit

The audit engine checks:
- **ROMs** — files vs XML database cross-reference, duplicates, completeness
- **Emulators** — executable health, file counts, config presence
- **Media** — wheels, videos, themes, artwork completeness per system
- **RocketLauncher** — modules, settings, profiles, plugins
- **HyperSpin XML** — database parsing, game entries, metadata quality
- **Health Score** — weighted 0–100 score per system and overall

## Web Dashboard

Modern dark-theme dashboard at `http://127.0.0.1:8888`:
- **Dashboard** — stats, health score, quick actions
- **Systems** — browse/filter all systems with health indicators
- **Emulators** — emulator inventory with health status
- **Backups** — create backups, view history
- **Updates** — update pipeline status and history
- **AI Assistant** — chat interface with DB query mode

## Plugin System

Drop Python files in `plugins/` with this structure:
```python
PLUGIN_NAME = "my_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "What it does"

def register(toolkit):
    # Called on load
    pass

def unregister():
    # Called on unload
    pass
```

## Configuration

Edit `config.yaml` to customize paths, AI settings, backup preferences, and dashboard options. All paths auto-expand environment variables.

## Repair Script

Run the automated repair script to check for common issues:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\repair.ps1
```

## 35-Milestone Roadmap

See [MILESTONES.md](MILESTONES.md) for the complete enhancement roadmap covering:
- Foundation (M1–M5): Config, DB, logging, backup, recovery
- Audit & Discovery (M6–M10): ROM, emulator, media, RL, XML auditing
- Safe Updates (M11–M15): Update manager, version tracking, rollback
- AI Integration (M16–M20): LLM layer, ROM ID, recommendations, NL queries
- Web Dashboard (M21–M25): FastAPI dashboard with full UI
- Advanced (M26–M35): Dedup, completion tracking, research agent, plugins, sync, benchmarks, health score, agentic orchestrator
