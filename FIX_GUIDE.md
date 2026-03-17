# HyperSpin Extreme Toolkit — Complete Fix Guide

## All Known Issues & Verified Fixes

---

## ISSUE 1: Corrupted Directory — `MAME - 0.211 and previous`

### Symptoms
```
Get-ChildItem : The file or directory is corrupted and unreadable.
Path: D:\Arcade\emulators\MAME - 0.211 and previous
```

### Root Cause
NTFS Master File Table (MFT) or directory index entries are damaged. This is typically caused by:
- Improper shutdown during file write
- Bad sectors on the hard drive
- Power loss during large file operations
- Disk aging on a nearly-full 12 TB drive

### Fix Procedure (Safe — No Data Loss)

**Step 1: Check disk health first (read-only scan)**
```powershell
# Read-only check — does NOT modify anything
chkdsk D: /scan
```
This performs an online scan and reports what it finds without fixing anything.

**Step 2: Review the output**
- If it reports "Windows has found errors", proceed to Step 3
- If it reports bad sectors, you may have a failing drive — back up critical data immediately

**Step 3: Fix filesystem errors (requires exclusive lock)**
```powershell
# This fixes directory index and MFT errors
# WARNING: D: drive will be locked during repair — close all programs using D:
chkdsk D: /f
```
- If Windows says the drive is in use, it will offer to schedule the check at next reboot
- Type `Y` and reboot — chkdsk will run before Windows loads

**Step 4: If bad sectors are suspected**
```powershell
# Full surface scan + repair (can take HOURS on 12 TB)
chkdsk D: /r
```
- `/r` includes `/f` plus scans for bad sectors and recovers readable data
- On a 12 TB drive this can take 4-12 hours — run overnight

**Step 5: Verify the fix**
```powershell
# After chkdsk completes and system reboots:
Get-ChildItem -Path "D:\Arcade\emulators\MAME - 0.211 and previous" -ErrorAction SilentlyContinue | Measure-Object
```
- If it returns a count, the directory is recovered
- If it still errors, the directory metadata is permanently lost — but files may be in `found.000` folder at D:\ root

### Alternative Recovery (if chkdsk fails)
```powershell
# Check for recovered file fragments
Get-ChildItem D:\found.000 -ErrorAction SilentlyContinue

# If the directory is unrecoverable, the old MAME versions (pre-0.211)
# are not needed for your current romset — they can be replaced by
# downloading the specific version you need from:
# https://github.com/mamedev/mame/releases
```

### Risk Assessment
| Action | Risk | Notes |
|---|---|---|
| `chkdsk /scan` | **NONE** | Read-only, safe to run anytime |
| `chkdsk /f` | **LOW** | Fixes metadata, minimal data risk |
| `chkdsk /r` | **LOW-MEDIUM** | Full surface scan, very slow on 12 TB |
| Delete corrupted dir | **LOW** | Old MAME versions, replaceable |

---

## ISSUE 2: MAME Version 0.228 — 50+ Versions Behind

### Current State
```
Installed: MAME 0.228 (January 2021)
Latest:    MAME 0.273+ (2025)
Gap:       50+ releases, hundreds of new drivers, thousands of fixes
```

### Why This Matters
- **New games**: ~50-100 new machines added per version
- **Driver fixes**: Games that didn't work in 0.228 may work now
- **ROM renames**: Some ROMs have been renamed/reorganized between versions
- **CHD format**: Some CHDs upgraded from v4 to v5
- **Security**: Older MAME has known bugs

### Safe Upgrade Procedure

**Phase 1: Snapshot (via toolkit)**
```bash
# Use the toolkit's safe update pipeline
python main.py backup create "D:\Arcade\emulators\MAME" --label "mame-0228-pre-upgrade" --type full
```

**Phase 2: Download Latest MAME**
```powershell
# Option A: From GitHub releases
# https://github.com/mamedev/mame/releases/latest
# Download: mame0273b_64bit.exe (self-extracting) or the zip

# Option B: Via toolkit release checker
python main.py releases check --emulator MAME
```

**Phase 3: Install Side-by-Side (don't overwrite yet)**
```powershell
# Extract new MAME to a temporary location
mkdir D:\Arcade\emulators\MAME_0273_new
# Extract downloaded MAME into this directory
```

**Phase 4: Generate New DAT and Audit ROMs**
```powershell
# Generate XML listxml for ROM auditing
D:\Arcade\emulators\MAME_0273_new\mame64.exe -listxml > D:\hyperspin_toolkit\output\mame0273.xml

# Use ClrMamePro or RomVault to:
# 1. Load the new DAT (mame0273.xml)
# 2. Scan your existing ROM directory
# 3. Generate a "have" vs "miss" report
# 4. Identify renamed/split/merged ROMs
```

**Phase 5: ROM Set Reconciliation**

MAME ROM set types and what happens during upgrade:

| Set Type | Description | Upgrade Impact |
|---|---|---|
| **Non-merged** | Each ROM zip is self-contained | Easiest to upgrade — just verify each zip |
| **Split** | Parent + clone structure | Need to update parent/clone relationships |
| **Merged** | Everything in one zip per parent | Largest zips, most efficient storage |

```
Common changes between MAME versions:
- ROM renames:  oldname.zip → newname.zip (ClrMamePro handles this)
- ROM splits:   game.zip → game.zip + device.zip (need new device ROMs)
- ROM merges:   game1.zip + game2.zip → game.zip (saves space)
- New ROMs:     Completely new dumps added (need to acquire)
- CHD updates:  Some CHDs re-dumped or format changed
```

**Phase 6: Apply and Test**
```powershell
# Once ROM audit is clean:
# 1. Rename current MAME directory
Rename-Item "D:\Arcade\emulators\MAME" "D:\Arcade\emulators\MAME_0228_backup"

# 2. Rename new MAME into place
Rename-Item "D:\Arcade\emulators\MAME_0273_new" "D:\Arcade\emulators\MAME"

# 3. Copy your config files from old to new
Copy-Item "D:\Arcade\emulators\MAME_0228_backup\cfg\*" "D:\Arcade\emulators\MAME\cfg\" -Recurse
Copy-Item "D:\Arcade\emulators\MAME_0228_backup\nvram\*" "D:\Arcade\emulators\MAME\nvram\" -Recurse
Copy-Item "D:\Arcade\emulators\MAME_0228_backup\hi\*" "D:\Arcade\emulators\MAME\hi\" -Recurse

# 4. Point MAME to your existing ROM path
# Edit D:\Arcade\emulators\MAME\ini\mame.ini:
#   rompath  D:\Arcade\emulators\MAME\roms

# 5. Quick verify
D:\Arcade\emulators\MAME\mame64.exe -verifyroms | Select-String "romset"
```

**Phase 7: Verify in RocketLauncher**
- Open RocketLauncher UI
- Navigate to MAME module settings
- Update the emulator path if needed
- Test launch 3-5 known-working games
- If problems: rollback by renaming directories back

**Phase 8: Commit or Rollback**
```bash
# If everything works:
python main.py update register MAME "D:\Arcade\emulators\MAME" --old-version 0.228 --new-version 0.273

# If problems — instant rollback:
# Rename MAME → MAME_0273_failed
# Rename MAME_0228_backup → MAME
```

### Risk Assessment
| Step | Risk | Mitigation |
|---|---|---|
| Download new MAME | **NONE** | Just downloading |
| Side-by-side install | **NONE** | Original untouched |
| ROM audit | **NONE** | Read-only scan |
| Directory rename | **LOW** | Instant reversible |
| Config copy | **LOW** | Backup preserved |
| RocketLauncher test | **LOW** | Config changes only |

---

## ISSUE 3: Only 60 GB Free on 12 TB Drive

### Current State
```
D:\ Drive: 11,116 GB used / 60 GB free / 11,176 GB total (99.5% full)
```

### Quick Wins for Space Recovery

**Win 1: Consolidate redundant emulator versions**
```bash
python main.py optimize emulators
```
Known redundancies found:
- **Xenia**: 7 copies (1.07, 1.11c, 1.11e, 1.11g, 1.11h, 1.11i, 1.11k) — keep only latest
- **PCSX2**: 2 copies (PCSX2, PCSX2 1.40) — keep newer
- **Dolphin**: 2 copies (Dolphin, Dolphin Triforce) — Triforce is separate, both needed
- **Yuzu**: Discontinued emulator — can be removed entirely if not in use
- **Estimated savings: 5-20 GB**

**Win 2: Remove corrupted directory (after attempting repair)**
```powershell
# Only after chkdsk attempt — if unrecoverable:
# The MAME 0.211 and previous versions are superseded by your 0.228 install
# Potential savings: several GB
```

**Win 3: Find and remove duplicate ROMs**
```bash
python main.py optimize duplicates --dir "D:\Arcade\emulators\MAME\roms"
```

**Win 4: Compress old backups**
```powershell
# Find large uncompressed backup files
python main.py optimize large-files --min-mb 500
```

**Win 5: Clean empty directories**
```bash
python main.py optimize report
```

### Space-Efficient Practices Going Forward
1. Use **TorrentZip** format for ROM archives (maximizes compression, standardized)
2. Use **merged** MAME ROM sets (smallest total size)
3. Enable **incremental backups** instead of full backups
4. Run space optimizer monthly via scheduled agent

---

## ISSUE 4: Multiple Outdated Emulators

### Emulators with Known GitHub Releases (Auto-Checkable)

Run this to check all at once:
```bash
python main.py releases check
```

| Emulator | Your Est. Date | Current Status | Action |
|---|---|---|---|
| **MAME** | Jan 2021 | 50+ versions behind | **UPGRADE** (see Issue 2) |
| **PCSX2** | ~2020 | Now v2.x with Qt UI | **UPGRADE** — massive improvements |
| **Dolphin** | ~2021 | Monthly releases | **UPGRADE** |
| **RPCS3** | ~2021 | Weekly builds | **UPGRADE** |
| **PPSSPP** | ~2021 | Major updates | **UPGRADE** |
| **Cemu** | ~2021 | Now open source | **UPGRADE** |
| **RetroArch** | ~2021 | Constant updates | **UPGRADE** — covers 100+ cores |
| **TeknoParrot** | ~2021 | Active development | **UPGRADE** |
| **Yuzu** | ~2021 | **DISCONTINUED** | Remove or keep as-is |
| **Citra** | ~2021 | **DISCONTINUED** | Remove or keep as-is |

### Safe Upgrade Workflow (applies to ALL emulators)
```
For each emulator:
1. python main.py backup create "D:\Arcade\emulators\{NAME}" --label "pre-upgrade"
2. python main.py releases check --emulator {NAME}
3. Download latest from GitHub releases
4. Extract to side-by-side directory
5. Copy config/saves from old to new
6. Test in RocketLauncher
7. Commit or rollback
```

---

## ISSUE 5: RocketLauncher Module Sync

### Problem
When emulators are upgraded, RocketLauncher module configs may need updating:
- Emulator paths change
- Command-line arguments change between versions
- New features may need new module settings

### Fix
```
After each emulator upgrade:
1. Open RocketLauncherUI
2. Navigate to the system using that emulator
3. Verify emulator path is correct
4. Test launch with a known-good ROM
5. Check module-specific settings (especially for MAME, Dolphin, PCSX2)
```

### Key RocketLauncher Paths
```
D:\Arcade\RocketLauncher\Settings\   — Global settings
D:\Arcade\RocketLauncher\Modules\    — Per-emulator modules (190+)
D:\Arcade\RocketLauncher\Profiles\   — Per-game configs
```

---

## ISSUE 6: HyperSpin XML Database Sync

### Problem
When ROM sets change (renames, additions, removals), HyperSpin XML databases become stale.

### Fix
```
After ROM set changes:
1. Run: python main.py audit system {SYSTEM_NAME}
2. Check for: missing_roms and extra_roms in output
3. Update XML using:
   - Don Bradman's HyperSpin Tools (manual)
   - Universal XML Scraper (automated via ScreenScraper)
   - python main.py audit full (reports all mismatches)
```

---

## Summary: Fix Priority Order

| Priority | Issue | Time | Risk | Impact |
|---|---|---|---|---|
| 1 | **chkdsk /scan on D:** | 5 min | NONE | Assess drive health |
| 2 | **Consolidate Xenia copies** | 15 min | LOW | Recover 5-15 GB |
| 3 | **Run space optimizer** | 30 min | NONE | Find all savings |
| 4 | **chkdsk /f on corrupted dir** | 30-60 min | LOW | Recover directory |
| 5 | **Upgrade MAME 0.228→latest** | 2-4 hours | LOW | Biggest improvement |
| 6 | **Upgrade PCSX2 to v2.x** | 1 hour | LOW | Major quality jump |
| 7 | **Upgrade RetroArch** | 1 hour | LOW | Updates 100+ cores |
| 8 | **Check all emulator updates** | 30 min | NONE | Awareness |
| 9 | **Full ecosystem audit** | 1 hour | NONE | Baseline health score |
