# HyperSpin Extreme Toolkit — User Guide

> **Just talk to Goose.** Everything else happens automatically.

---

## Getting Started

### Prerequisites (one-time setup)

1. **Install Goose Desktop** from the v1.27.2 release, or run:
   ```powershell
   .\setup\install_goose.ps1
   ```

2. **Start LM Studio** — load a model — click **Start Server** (port 1234).
   - Best overall: `Devstral-Small-2-24B Q4_K_M`
   - Best long context: `Qwen3.5-9B Opus 4.6 Q8`

3. **Open Goose Desktop** → Settings → Provider: **LM Studio** → URL: `http://localhost:1234/v1`

4. **Verify the stack:**
   ```powershell
   python D:\hyperspin_toolkit\setup\goose_setup.py --e2e
   ```

5. **Start OpenHands** (optional — needed for batch file edits):
   ```powershell
   docker run -it -p 3000:3000 -e SANDBOX_RUNTIME_CONTAINER_IMAGE=docker.all-hands.dev/all-hands-ai/runtime:latest docker.all-hands.dev/all-hands-ai/openhands:latest
   ```

---

## How to Use: Just Talk to Goose

You never need to type a command. Open Goose and describe what you want in plain English. The four agents (Toolkit MCP, CLI-Anything, NemoClaw, OpenHands) activate automatically based on your intent.

---

## Usage Examples by Goal

---

### Health Check

**Say:** "Run a full audit of my HyperSpin collection"

**What activates:**
- Goose loads `hyperspin-audit` skill
- Toolkit MCP: `audit_full()` — scans all 184 systems
- NemoClaw `EmulatorSpecialist` — reasons over the results
- Goose presents: health score, top issues, prioritised fix list

**Example result:**
```
Overall Health Score: 67.3%
  MAME:           42% — version 0.228, 45 versions behind
  Nintendo 64:    91% — healthy
  PlayStation 2:  55% — emulator path broken
  23 systems below 50%
  Disk free: 60 GB — CRITICAL

Top Recommendations:
  1. Update MAME from 0.228 to 0.273
  2. Fix broken emulator path for PlayStation 2
  3. Free 50+ GB via duplicate ROM removal
```

---

### Emulator Updates

**Say:** "What emulator updates are available?"

**Or more specific:** "Is PCSX2 up to date?" / "Check Dolphin"

**What activates:**
- Toolkit MCP: `check_all_updates()` or `check_emulator_update("PCSX2")`
- NemoClaw `UpdateOrchestrator` — ranks updates by impact + safety

**Example result:**
```
Emulator Update Status (20 tracked):
  MAME        0.228 → 0.273  UPDATE AVAILABLE  [HIGH PRIORITY]
  PCSX2       1.7.3 → 2.3.1  UPDATE AVAILABLE  [MEDIUM]
  Dolphin     5.0   → 2506   UPDATE AVAILABLE  [MEDIUM]
  RetroArch   1.16  → 1.19   UPDATE AVAILABLE  [LOW]
  RPCS3       0.0.28→ 0.0.31 UPDATE AVAILABLE  [MEDIUM]
  Cemu        2.0   → 2.4    OK
  ...

8 updates available. Recommended update order:
  1. MAME (highest impact, 45 versions gap)
  2. PCSX2 (major new compatibility features)
  3. Dolphin + RetroArch (low risk)
```

---

### Free Up Disk Space

**Say:** "How much disk space can I safely recover?"

**Or:** "Find duplicate ROMs" / "Clean up my emulators folder"

**What activates:**
- Toolkit MCP: `optimize_report()` — full analysis
- Toolkit MCP: `find_duplicates()` — hash-based scan
- Toolkit MCP: `find_redundant_emulators()` — version analysis
- NemoClaw `SpaceOptimizer` — prioritises recovery options

**Example result:**
```
Current: 12.06 TB used, 60 GB free  [CRITICAL]

Space Recovery Opportunities:
  Duplicate ROMs:          67.3 GB  [LOW RISK — safe to delete dupes]
  Redundant emulators:     18.2 GB  [LOW RISK — keep newest only]
  Large archive orphans:   12.0 GB  [MEDIUM — verify before delete]
  Old backup files:         8.5 GB  [LOW RISK — older than 30 days]

Total recoverable:  ~106 GB

Recommended first step: python main.py optimize duplicates
  Shows you the exact duplicate files before anything is deleted.
```

---

### Safe Emulator Update

**Say:** "Update MAME safely" / "Upgrade MAME to the latest version"

**What activates (full pipeline):**

```
Step 1: NemoClaw UpdateOrchestrator — generates safe update plan
Step 2: Toolkit MCP: backup_create() — snapshot MAME directory
Step 3: Toolkit MCP: check_emulator_update("MAME") — confirm latest version
Step 4: Goose presents download link + instructions
Step 5: After download: OpenHands batch-updates all RocketLauncher INI paths
Step 6: Toolkit MCP: audit_system("MAME") — confirms health improved
```

**You only need to approve each step.** Goose handles the sequencing.

---

### Fix a Specific System

**Say:** "PlayStation 2 has a health score of 35% — fix it"

**What activates:**
- Toolkit MCP: `audit_system("PlayStation 2")` — detailed breakdown
- NemoClaw `EmulatorSpecialist` — diagnoses the specific issues
- CLI-Anything — translates fix recommendations into commands
- Goose presents: exact steps with confidence scores

**Example fix plan:**
```
PlayStation 2 — Health 35%
Issues found:
  1. PCSX2 executable not found at D:\Arcade\emulators\PCSX2\pcsx2.exe
     Fix: Update emulator path or re-download PCSX2
  2. RocketLauncher module path incorrect
     Fix: openhands_update_ini("PlayStation 2", "Emulator Path", "D:\Arcade\emulators\PCSX2_new")
  3. 847 ROMs in directory, only 234 in XML database
     Fix: python main.py audit system "PlayStation 2" --repair-xml

Shall I proceed? [Yes/No]
```

---

### Analyse Media Quality

**Say:** "Check the artwork quality for my SNES collection"

**Or:** "Analyse the wheel logos for arcade" / "Is my media complete?"

**What activates:**
- Toolkit MCP: `audit_system("Super Nintendo")` — coverage report
- NemoClaw `MediaSpecialist` — analysis and scraping recommendations
- `ai vision` (optional) — GLM-4.6V-Flash analyses actual images

**Example result:**
```
SNES Media Coverage:
  Wheel logos:    94%  (823/875 games)
  Artwork:        67%  (587/875 games)
  Screenshots:    41%  (359/875 games)
  Video snaps:    12%  (105/875 games)

MediaSpecialist Recommendations:
  1. Use Skyscraper to fill artwork gaps (high quality, free)
  2. EmuMovies FTP has SNES video pack (bulk download)
  3. 52 wheel logos are wrong size — should be 400px min width
```

---

### Connecting a New Drive / Drive Letter Changed

**Say:** "I plugged in my 20TB drive — set it up" / "My drive letters changed again"

**What activates:**
- Goose loads `drive_manager` extension
- `drives_scan()` — detects all connected drives and which contain arcade content
- `drives_set()` — assigns the correct drive to the primary role
- Toolkit MCP: `reload_config()` — all paths update automatically

**Example result:**
```
Connected drives:
  D:  12.1 TB   ARCADE_10TB     HyperSpin ✓  RocketLauncher ✓  ROMs ✓  [PRIMARY]
  E:  18.6 TB   ARCADE_20TB     HyperSpin ✓  ROMs ✓                     [unassigned]
  F:   1.8 TB   GAMES_2TB       ROMs ✓                                  [unassigned]

Assigned D: as primary. All toolkit paths updated.
```

**Or just say:** "Scan my drives" / "Which drive has my arcade games?"

---

### Moving Collection to a Larger Drive (10TB → 20TB etc.)

**Say:** "Move my arcade collection from D: to the new 20TB drive at E:"

**Or:** "Transfer my games to E:\Arcade" / "Copy everything to the new drive"

**What Goose does (always checks space first, always dry-runs first):**

```
Step 1: drives_plan() — check how much space is needed vs available
        → Need: 10.8 TB   Available on E: 18.6 TB   Fits: YES

Step 2: drives_migrate(dry_run=True) — show what will be copied
        → 284,723 files  (10.8 TB)
        → 0 already done (fresh transfer)

Step 3: [You approve]

Step 4: drives_migrate(dry_run=False) — execute
        → Progress: 34%  3.7 TB / 10.8 TB  420 MB/s  ETA: 4h 12m
        → Resumable: if interrupted, re-run to continue from checkpoint

Step 5: RocketLauncher INI paths auto-rewritten (D:\ → E:\)
        → 1,847 .ini files updated   (23,104 path references)

Step 6: drives set primary E — toolkit switches to new drive
```

**Transfer is resumable** — if it stops (power loss, disconnect), just say "continue the transfer" and it picks up where it left off.

**Selective transfer** (e.g. ROMs only to save time):
> "Copy only the ROMs and emulators to the new drive, not media yet"

---

### Check Drive Health Before Copying

**Say:** "Is my 20TB drive healthy before I transfer everything to it?"

**What activates:**
- `drives_health()` — SMART status, temperature, reallocated sectors

**Example result:**
```
Drive E: Health
  Device:      WDC WD200EMAZ-11G4A0 (USB attached)
  SMART:       PASSED
  Temperature: 34°C
  Reallocated: 0  (0 = perfect)
  Power-on:    2,847 hours  (~0.3 years)
  Free:        18.6 TB of 20.0 TB
```

If SMART shows FAILED or reallocated sectors > 5, Goose will warn you **before** you start copying.

---

### Verify Migration Completed Correctly

**Say:** "Did everything copy over correctly to E:?" / "Compare D: and E: arcade folders"

**What activates:**
- `drives_compare()` — scans both trees and reports missing/extra/size-mismatched files

**Example result:**
```
Compare: D:\Arcade ↔ E:\Arcade
  Source files:  284,723
  Dest files:    284,720
  Status:        DIFFERENCES FOUND

  Missing on dest:    3 files  (2.4 GB)
  Extra on dest:      0 files
  Size mismatches:    1 file   (800 MB)

Missing on dest:
  ROMs\MAME\dkong.zip
  ROMs\MAME\pacman.zip
  emulators\PCSX2\pcsx2.exe

Tip: Run 'drives sync D:\Arcade E:\Arcade' to copy missing files.
```

---

### Keep a Second Drive Current (After Adding New Games)

**Say:** "Sync the new games I added to my backup drive" / "Update E: with what's new on D:"

**What activates:**
- `drives_compare()` — shows what's new first
- `drives_sync()` — copies only the new/changed files (skips everything already there)

**Key difference from migrate:** Sync only copies files that are *new or changed* — skips the 280,000 files already on the second drive. A 10TB collection that's 99% in sync takes minutes, not hours.

```
Syncing D:\Arcade → E:\Arcade
  [10%]  28.3 GB / 45.2 GB  380 MB/s  ETA 1m42s  1,247/4,891 files
  [50%]  22.6 GB / 45.2 GB  410 MB/s  ETA 0m32s  2,445/4,891 files
  [100%] 45.2 GB / 45.2 GB  395 MB/s            4,891/4,891 files

Sync Complete
  Copied:   4,891 files  (45.2 GB)
  Skipped:  279,832 files  (already current)
  Failed:   0
  Time:     1h 56m 14s
```

---

### Rebuild MAME Database

**Say:** "Rebuild my MAME HyperSpin database from scratch"

**What activates:**
```
Step 1: Toolkit MCP: mame_version() — locate MAME binary
Step 2: Toolkit MCP: mame_listxml() — run MAME -listxml (2-5 min)
Step 3: OpenHands: generate filtered HyperSpin XML
         (filters to ROMs you actually have in D:\Arcade\ROMs\MAME)
Step 4: Toolkit MCP: audit_system("MAME") — verify XML
```

---

### Ask the AI Anything

**Say:** "Why is my Dreamcast emulator not working in HyperSpin?"

**Or:** "What's the best emulator for PS2 games with a 3090?"
**Or:** "Explain what health score means"

**What activates:**
- Goose loads `hyperspin-ai` skill
- Uses local LLM directly (no MCP tool call needed)
- Answers from HyperSpin/emulation knowledge baked into the skill

---

### Vision Analysis

**Say:** "Check if my arcade wheel logos are good quality"

**What activates:**
- Goose: `ai vision D:\Arcade\HyperSpin\Media\MAME\Images\Wheel --batch`
- GLM-4.6V-Flash analyses each image
- Reports quality score, orientation issues, resolution problems

---

## Working with Agents Directly

If you want to talk directly to a specialist:

> *"Ask the ROM specialist: what's wrong with my MAME ROM set?"*

> *"Tell the Space Optimizer to find everything I can safely delete"*

> *"Ask the Update Orchestrator to plan a safe batch update of all emulators"*

Goose routes to the correct NemoClaw agent automatically.

---

## Safety: What Goose Will Always Do

Goose follows this safety protocol for every destructive action:

1. **Backup first** — `backup_create()` before any file modification
2. **Audit first** — baseline health score before changes
3. **Show you the plan** — presents what it will do and asks for approval
4. **Execute step by step** — one phase at a time, with verification after each
5. **Rollback available** — `backup rollback <id>` undoes any change

You will **always be asked to confirm** before:
- Deleting any files
- Overwriting emulator configurations
- Restoring backups
- Moving or renaming emulator directories

---

## Conversation Examples

### Example 1 — Quick question
```
You:   What version of MAME do I have?
Goose: Checking... MAME 0.228 at D:\Arcade\emulators\MAME\mame64.exe
       Latest version: 0.273. You are 45 versions behind.
       Want me to plan a safe upgrade?
```

### Example 2 — Multi-step task
```
You:   I have 60GB free and I'm scared to update MAME in case it breaks.
       Walk me through it safely.

Goose: Here's the safe plan for MAME 0.228 → 0.273:

       Phase 1 (now): Create backup snapshot of current MAME
         → backup_create("D:\Arcade\emulators\MAME", label="pre-upgrade-0228")
         → ~2.3 GB, ~3 minutes

       Phase 2: Download MAME 0.273 to NEW folder (don't overwrite 0.228)
         → D:\Arcade\emulators\MAME_0273_test\
         → Download: https://github.com/mamedev/mame/releases/...

       Phase 3: Test with 5 known-working games
         → I'll run a quick verify-roms check

       Phase 4: If tests pass — update all RocketLauncher INI paths
         → OpenHands will update all 173 emulator configs automatically

       Phase 5: Run audit to confirm health improved

       Ready to start Phase 1? [Yes / Not yet]
```

### Example 3 — Ambiguous request
```
You:   Clean up my stuff

Goose: I'll interpret "clean up" as freeing disk space safely.
       Running space analysis...

       Found:
         Duplicate ROMs:    67.3 GB (4,821 duplicate files)
         Redundant emus:    18.2 GB (MAME 0.225, 0.226, 0.227 all present)
         Old backups:        8.5 GB (>30 days old)

       Total: ~94 GB recoverable

       Safest starting point: Remove 3 old MAME versions (keep 0.228).
       Estimated recovery: 18.2 GB. Risk: None (working copy untouched).

       Shall I show you exactly which files? [Yes / No]
```

---

## Troubleshooting

### "Goose says it can't find the hyperspin_toolkit extension"

Check Goose → Settings → Extensions — `hyperspin_toolkit` should be listed and enabled.
If not: run `python D:\hyperspin_toolkit\setup\goose_setup.py --fix`

### "LM Studio is not running / no model loaded"

Open LM Studio → load a model → click the API server button (green play button, port 1234).
Then re-try in Goose.

### "OpenHands is not available"

The OpenHands bridge is optional. Without it, Goose can still:
- Run all 21 Toolkit MCP tools
- Use all 6 NemoClaw agents
- Use CLI-Anything to translate commands
- Ask you to run multi-file commands manually

Start OpenHands with the Docker command in the Prerequisites section.

### "My drive letter changed and paths are broken"

```powershell
python main.py drives scan           # See what's connected
python main.py drives auto           # Auto-reassign roles
python main.py drives set primary E  # Or set manually
```

Or tell Goose: "My drive letters changed — re-scan and fix the paths"

### "Transfer stopped halfway — how do I resume?"

Just re-run the same migrate command — it automatically skips already-copied files:
```powershell
python main.py drives migrate "D:\Arcade" "E:\Arcade"
```
The transfer manifest at `E:\Arcade\.hstk_transfer_manifest.json` tracks progress.

### "RocketLauncher can't find games after moving drives"

The INI path rewriter fixes this:
```powershell
python main.py drives rewrite-paths "E:\Arcade\RocketLauncher" D E
python main.py drives rewrite-paths "E:\Arcade\RocketLauncher" D E --dry-run  # preview first
```
Or tell Goose: "Fix the RocketLauncher paths after my drive moved from D: to E:"

### "The NemoClaw agent is slow"

NemoClaw agents call the local LLM, which can take 15-60 seconds on large models.
Switch to `Qwen3.5-9B Q8` for faster agent responses (excellent quality, 9B size).

### "I want to undo something"

```
python main.py backup list
python main.py backup rollback <ID>
```

Or tell Goose: "Rollback the last change I made to MAME"
