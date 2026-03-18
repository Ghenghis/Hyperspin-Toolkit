# HyperSpin Extreme Toolkit — Quick Reference

---

## Goose Natural Language Triggers

These phrases reliably activate the correct skill + agent chain:

| Say this...                      | Activates                                          |
| -------------------------------- | -------------------------------------------------- |
| "audit my collection"            | `hyperspin-audit` + `audit_full` MCP               |
| "audit [system name]"            | `hyperspin-audit` + `audit_system` MCP             |
| "check emulator updates"         | `hyperspin-releases` + `check_all_updates` MCP     |
| "is [emulator] up to date?"      | `hyperspin-releases` + `check_emulator_update` MCP |
| "free up disk space"             | `hyperspin-optimize` + `optimize_report` MCP       |
| "find duplicate ROMs"            | `hyperspin-optimize` + `find_duplicates` MCP       |
| "update [emulator] safely"       | `hyperspin-update` + UpdateOrchestrator NemoClaw   |
| "fix [system name]"              | `hyperspin-toolkit` + EmulatorSpecialist NemoClaw  |
| "backup [path]"                  | `hyperspin-backup` + `backup_create` MCP           |
| "rollback" / "undo changes"      | `hyperspin-backup` + `backup list`                 |
| "upgrade MAME"                   | `hyperspin-mame` + UpdateOrchestrator + OpenHands  |
| "rebuild MAME database"          | `hyperspin-mame` + `mame_listxml` + OpenHands      |
| "analyse audit results"          | `hyperspin-ai` + `ai_analyse`                      |
| "check media quality"            | `hyperspin-vision` + MediaSpecialist NemoClaw      |
| "analyse [image path]"           | `hyperspin-vision` + `ai vision`                   |
| "plan a big cleanup"             | `hyperspin-orchestrator` + `nemoclaw_plan`         |
| "do everything"                  | `hyperspin-orchestrator` + all 4 agents            |
| "scan my drives"                 | `drive_manager` + `drives_scan` MCP                |
| "which drive has my games?"      | `drive_manager` + `drives_scan` MCP                |
| "switch to the 20TB drive"       | `drive_manager` + `drives_set` MCP                 |
| "move collection to new drive"   | `drives_migrate` + `drives_plan` MCP               |
| "will my games fit on E:?"       | `drives_plan` MCP                                  |
| "check drive health"             | `drives_health` MCP                                |
| "fix drive letter in INI files"  | `drives rewrite-paths` CLI                         |
| "compare D and E arcade folders" | `drives_compare` MCP                               |
| "sync new games to second drive" | `drives_sync` MCP                                  |
| "keep my backup drive current"   | `drives_sync` MCP                                  |

---

## MCP Tools (70+ total — called by Goose automatically)

> **Note:** The table below shows the original core tools. The full MCP bridge (`mcp_bridge.py`) now includes 70+ tools covering all 66 milestones — ROM audit, media audit, XML tools, emulator health, version tracking, dependency detection, snapshots, rollbacks, event hub, NL query, game recommender, troubleshooter, drive management, BIOS verification, DAT verification, metadata scraping, HyperSpin settings, frontend conversion, RL media/stats, scheduling, agent memory, self-healing, drive fingerprinting, gstack roles, and more. Run `python mcp_bridge.py --list-tools` for the complete list.

| Tool                       | Required Args               | What it does                             |
| -------------------------- | --------------------------- | ---------------------------------------- |
| `audit_full`               | —                           | Full ecosystem audit, all 184 systems    |
| `audit_system`             | `system_name`               | Single system audit                      |
| `check_all_updates`        | —                           | All 20+ emulators vs GitHub releases     |
| `check_emulator_update`    | `emulator_name`             | Single emulator update check             |
| `optimize_report`          | —                           | Full space optimization report           |
| `find_duplicates`          | `directory?`                | Hash-based duplicate ROM finder          |
| `find_redundant_emulators` | —                           | Multi-version emulator detection         |
| `find_large_files`         | `min_size_mb?`              | Largest files (default 500 MB+)          |
| `discover_tools`           | —                           | Check MAME, Igir, Flips, 7z...           |
| `backup_create`            | `source`, `label?`          | Versioned directory backup               |
| `get_stats`                | —                           | Systems / ROMs / emulators counts        |
| `disk_usage`               | —                           | Drive used/free/total                    |
| `mame_version`             | —                           | MAME version + exe path                  |
| `mame_listxml`             | `output_file?`              | Run MAME -listxml, save XML              |
| `drives_scan`              | `min_gb?`                   | Scan all drives, detect arcade content   |
| `drives_status`            | —                           | Show primary/secondary/tertiary + usage  |
| `drives_set`               | `role`, `letter`            | Assign drive letter to a role            |
| `drives_plan`              | `source_root`, `dest_drive` | Space check before migrating             |
| `drives_migrate`           | `source_root`, `dest_root`  | Copy collection, resume, rewrite INIs    |
| `drives_health`            | `letter`                    | SMART status, temp, reallocated sectors  |
| `drives_compare`           | `source_root`, `dest_root`  | Diff two dirs — missing/extra/mismatched |
| `drives_sync`              | `source_root`, `dest_root`  | Incremental sync — copy only new/changed |

---

## NemoClaw Agents (6 specialists)

| Agent                | Keyword triggers                               | Best for                                         |
| -------------------- | ---------------------------------------------- | ------------------------------------------------ |
| `RomSpecialist`      | rom, hash, dat, verify, parent, clone          | ROM validation, missing ROMs, MAME parent-clone  |
| `EmulatorSpecialist` | emulator, config, rocketlauncher, path, ini    | Broken emulator, wrong paths, module config      |
| `MediaSpecialist`    | media, artwork, wheel, snap, video, scrape     | Coverage gaps, quality issues, scraping advice   |
| `DatabaseSpecialist` | xml, database, listxml, sync, gamelist         | HyperSpin XML rebuild, game list sync            |
| `SpaceOptimizer`     | space, disk, duplicate, clean, delete, archive | Space recovery, safe deletion, duplicate removal |
| `UpdateOrchestrator` | update, upgrade, latest, version, batch        | Safe multi-emulator update plans                 |

**Direct agent call:**
```
"Ask the ROM Specialist: are my MAME ROMs complete?"
"Tell the Space Optimizer to analyse everything I can safely delete"
"UpdateOrchestrator: plan a safe batch upgrade of all 8 pending updates"
```

---

## CLI-Anything Bridge

Translates your words into exact toolkit commands. Used by Goose automatically but also available standalone:

```powershell
# Translate only (returns command + confidence score)
python engines\cli_anything_bridge.py "check MAME update"
# → python main.py releases check --emulator MAME  [confidence: 1.00]

python engines\cli_anything_bridge.py "find space I can recover"
# → python main.py optimize report  [confidence: 0.92]
```

---

## Direct CLI Commands (main.py)

### Audit
```powershell
python main.py audit full                    # Full ecosystem audit
python main.py audit system "MAME"           # Single system
python main.py audit emulators               # All emulators
```

### Backup
```powershell
python main.py backup create "D:\Arcade\emulators\MAME" --label "pre-upgrade"
python main.py backup list                   # Show all backups with IDs
python main.py backup rollback 3             # Rollback to backup ID 3
python main.py backup restore <dir> <target> # Manual restore
```

### Releases / Updates
```powershell
python main.py releases check                # All emulators
python main.py releases check -e MAME        # One emulator
python main.py releases report               # Save full JSON report
```

### Space Optimization
```powershell
python main.py optimize report               # Full analysis + recommendations
python main.py optimize duplicates           # Find duplicate ROMs
python main.py optimize emulators            # Find redundant emulator versions
python main.py optimize large-files          # Files over 500 MB
python main.py optimize large-files --min-mb 1000  # Files over 1 GB
```

### AI Assistant
```powershell
python main.py ai ask "Why is my Dreamcast emulator not working?"
python main.py ai analyse --last-audit       # Analyse latest audit with LLM
python main.py ai analyse --focus emulators  # Focus on emulators only
python main.py ai vision "D:\Arcade\HyperSpin\Media\MAME\Images\Wheel\pacman.png"
python main.py ai vision "D:\Arcade\HyperSpin\Media\MAME\Images\Wheel" --batch --save
python main.py ai query "how many systems have health score below 50%"
python main.py ai status                     # Check LM Studio + Ollama
```

### External Tools
```powershell
python main.py tools discover                # Check what's installed
python main.py tools mame-version            # MAME version + path
python main.py tools mame-verify             # Verify ROM integrity
python main.py tools mame-listxml            # Generate XML database
python main.py tools mame-listxml --hyperspin  # + convert to HyperSpin XML
python main.py tools mame-listxml --roms-dir "D:\Arcade\ROMs\MAME"  # filter to owned ROMs
```

### Multi-Drive Management
```powershell
# Scan & detect
python main.py drives scan                   # Show all connected drives + arcade content
python main.py drives scan --min-gb 500      # Only drives ≥ 500 GB
python main.py drives status                 # Show assigned roles + live usage

# Assign drives (run after connecting a new HDD)
python main.py drives auto                   # Auto-detect and assign primary/secondary
python main.py drives auto --dry-run         # Preview without saving
python main.py drives set primary E          # Manually set E: as primary
python main.py drives set secondary F        # F: as secondary (overflow)
python main.py drives set primary E --root Arcade  # Custom subfolder name
python main.py drives clear all              # Reset all assignments

# Space planning before transfer
python main.py drives plan "D:\Arcade" E                        # Will it fit?
python main.py drives plan "D:\Arcade" F --category roms        # ROMs only
python main.py drives plan "D:\Arcade" F -c roms -c emulators   # ROMs + emus

# Migrate collection to larger drive (10TB → 20TB etc.)
python main.py drives migrate "D:\Arcade" "E:\Arcade" --dry-run   # Preview first
python main.py drives migrate "D:\Arcade" "E:\Arcade"             # Full copy
python main.py drives migrate "D:\Arcade" "E:\Arcade" --verify    # + hash verify
python main.py drives migrate "D:\Arcade" "E:\Arcade" -c roms -c emulators  # Selective
# Transfer is resumable — re-run same command to continue after interruption

# Fix drive letter references in RocketLauncher INIs after migration
python main.py drives rewrite-paths "E:\Arcade\RocketLauncher" D E  # D→E
python main.py drives rewrite-paths "E:\Arcade\RocketLauncher" D E --dry-run

# HDD health check
python main.py drives health D               # SMART status for D:
python main.py drives health --all-drives    # All non-system drives

# Compare two drives (verify migration or see what needs syncing)
python main.py drives compare "D:\Arcade" "E:\Arcade"              # Missing/extra/mismatch
python main.py drives compare "D:\Arcade" "E:\Arcade" --show-extra # Also list extra on dest
python main.py drives compare "D:\Arcade" "E:\Arcade" --no-size-check  # Fast mode

# Incremental sync (day-to-day: only copies new/changed files)
python main.py drives sync "D:\Arcade" "E:\Arcade" --dry-run       # Preview what will sync
python main.py drives sync "D:\Arcade" "E:\Arcade"                 # Copy new/changed only
python main.py drives sync "D:\Arcade" "E:\Arcade" --verify        # + hash verify
python main.py drives sync "D:\Arcade" "E:\Arcade" --delete-extra  # Mirror mode (removes orphans)
```

### Stats & Dashboard
```powershell
python main.py stats                         # Collection statistics
python main.py dashboard                     # Launch web UI at :8888
python main.py init                          # First-time system discovery
```

### Update Pipeline
```powershell
python main.py update register "MAME" "D:\Arcade\emulators\MAME" --old-version 0.228 --new-version 0.273
python main.py update queue                  # Pending updates
python main.py update history                # Past updates
```

### Agents (direct)
```powershell
python main.py agent list                    # All available agents
python main.py agent run RomSpecialist "validate MAME ROMs"
```

---

## OpenHands Tasks (via Goose or direct bridge)

Tell Goose to use OpenHands for tasks involving many files at once:

```
"Use OpenHands to update all RocketLauncher INI paths from
 D:\Arcade\emulators\MAME to D:\Arcade\emulators\MAME_0273"

"Use OpenHands to generate a HyperSpin XML for MAME
 using only the ROMs in D:\Arcade\ROMs\MAME"

"Use OpenHands to find and fix all broken emulator paths
 across every RocketLauncher module"
```

Direct bridge check:
```powershell
python engines\openhands_bridge.py status    # Is OpenHands running?
```

---

## Setup & Validation

```powershell
# Full stack health check
python setup\goose_setup.py --e2e

# Install / update Goose v1.27.2
.\setup\install_goose.ps1

# Re-install only (skip E2E test)
.\setup\install_goose.ps1 -SkipValidation

# Force re-download even if installed
.\setup\install_goose.ps1 -Force
```

---

## Key File Locations

| What                 | Where                                                        |
| -------------------- | ------------------------------------------------------------ |
| Goose config         | `%APPDATA%\Block\goose\config\config.yaml`                   |
| Goose skills         | `%APPDATA%\Block\goose\config\skills\`                       |
| LM Studio MCP config | `C:\Users\Admin\.lmstudio\mcp.json`                          |
| LM Studio settings   | `C:\Users\Admin\.lmstudio\settings.json`                     |
| Toolkit root         | `D:\hyperspin_toolkit\`                                      |
| MCP bridge           | `D:\hyperspin_toolkit\mcp_bridge.py`                         |
| CLI-Anything bridge  | `D:\hyperspin_toolkit\engines\cli_anything_bridge.py`        |
| NemoClaw agents      | `D:\hyperspin_toolkit\engines\nemoclaw_agents.py`            |
| OpenHands bridge     | `D:\hyperspin_toolkit\engines\openhands_bridge.py`           |
| Audit output         | `D:\HyperSpin_Toolkit_Output\latest_audit.json`              |
| Optimize output      | `D:\HyperSpin_Toolkit_Output\space_optimization_report.json` |
| MAME listxml         | `D:\HyperSpin_Toolkit_Output\mame_listxml.xml`               |
| Arcade collection    | `D:\Arcade\`                                                 |

---

## Goose Skill Map

| Skill                    | Loaded when you say...                     |
| ------------------------ | ------------------------------------------ |
| `hyperspin-toolkit`      | general collection questions               |
| `hyperspin-audit`        | audit, health, scan, check                 |
| `hyperspin-update`       | update, upgrade, install new version       |
| `hyperspin-optimize`     | space, disk, duplicate, clean              |
| `hyperspin-backup`       | backup, snapshot, rollback, undo           |
| `hyperspin-releases`     | latest version, GitHub, release, changelog |
| `hyperspin-mame`         | MAME, listxml, romset, arcade              |
| `hyperspin-ai`           | ask, explain, analyse, why, how            |
| `hyperspin-vision`       | image, artwork, media, quality, screenshot |
| `hyperspin-orchestrator` | everything, plan, coordinate, do it all    |
| `hyperspin-cli-anything` | run command, execute, translate            |

---

## Health Score Reference

| Score   | Meaning   | Action                           |
| ------- | --------- | -------------------------------- |
| 90-100% | Excellent | Maintenance only                 |
| 75-89%  | Good      | Fix minor issues when convenient |
| 50-74%  | Fair      | Schedule a repair session        |
| 25-49%  | Poor      | Address this week                |
| 0-24%   | Critical  | Fix before using HyperSpin       |

---

## Emulators Tracked for Updates (20+)

MAME, RetroArch, Dolphin, PCSX2, RPCS3, PPSSPP, Cemu, Yuzu/Ryujinx, Snes9x, FCEUX, 
VisualBoyAdvance-M, DuckStation, Xemu (Xbox), PCFX, WinUAE (Amiga), VICE (C64),
Flycast (Dreamcast), redream, BigPEmu (Jaguar), melonDS (DS), mGBA

---

## Common Quick Fixes

| Problem                  | Command                                                    |
| ------------------------ | ---------------------------------------------------------- |
| MAME not found           | `python main.py tools discover`                            |
| Broken emulator path     | Tell Goose: "Fix emulator path for [system]"               |
| Low disk space           | `python main.py optimize report`                           |
| MAME database outdated   | `python main.py tools mame-listxml --hyperspin`            |
| Unknown health issue     | `python main.py audit full` then `ai analyse --last-audit` |
| Rollback needed          | `python main.py backup list` then `backup rollback <id>`   |
| LM Studio not responding | Check port 1234, model loaded, API server enabled          |
| OpenHands not reachable  | `docker ps` — check container is running on port 3000      |
