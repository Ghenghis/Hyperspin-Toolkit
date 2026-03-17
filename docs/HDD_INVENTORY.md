# HDD Inventory — HyperSpin Toolkit

> **Last Updated:** 2026-03-17  
> **Machine Registry:** `drive_registry.json` (serial-based identification)

---

## Quick Reference

| Letter | Label | Size | Health | Role | Collection Type | Backup Status |
|--------|-------|------|--------|------|-----------------|---------------|
| **D:** | Hyperspin_12T | 11,176 GB | ⚠ Warning | **TESTING** | HyperSpin + RL (184 sys) | Clone of I: |
| **I:** | Hyperspin_12T | 11,176 GB | ✅ Healthy | Active Primary | HyperSpin + RL (184 sys) | D: is clone |
| **K:** | HyperSpin Attraction | 11,176 GB | ✅ Healthy | Backup | Attract Mode (199 coll, 55 emu) | Not in use |
| **L:** | Super Game HDD | 11,176 GB | ⚠ Warning | Active Primary | CORE - TYPE R | → H: (pending clone) |
| **H:** | Retro_14tb | 13,039 GB | ✅ Healthy | Backup Target | Empty | Waiting for L: clone |
| **J:** | 20_TB | 18,627 GB | ✅ Healthy | ROM Backup | Switch ROMs + PC Games | Needs 22TB backup |
| **E:** | Archive2023 | 3,726 GB | ✅ Healthy | Archive | AI Models / Software / ISOs | No backup |
| **M:** | BATOCERA | 7 GB | ✅ Healthy | Boot | Batocera OS Boot (FAT32) | No backup |
| **N:** | Batocera | 1,856 GB | ⚠ Warning | Active Primary | Batocera Games (219 sys) | No backup |

### System Drives (Not Gaming)

| Letter | Label | Size | Model | Notes |
|--------|-------|------|-------|-------|
| C: | Windows X-Lite | 3,815 GB | addlink M.2 NVMe | Primary OS |
| F: | Windows X-Lite | 3,726 GB | Crucial CT4000P3PSSD8 | Secondary OS/Apps |
| G: | (none) | 3,726 GB | Samsung 990 EVO Plus 4TB | General Storage SSD |

---

## Detailed Drive Profiles

### 🔴 D: — TEST_HYPERSPIN (TESTING DRIVE)

| Property | Value |
|----------|-------|
| **Tag** | `TEST_HYPERSPIN` |
| **Rename To** | `Test_Hyperspin_Test` |
| **Physical Disk** | Disk 3 |
| **Model** | Seagate ST12000N M0127 |
| **Serial** | `7E0538EE1A62` |
| **Capacity** | 11,176 GB (12TB) |
| **Free Space** | 60 GB (0.5%) |
| **Filesystem** | NTFS |
| **Health** | ⚠ **Warning** — filesystem issues detected |
| **Interface** | SCSI/USB |
| **Collection** | HyperSpin + RocketLauncher |
| **Systems** | 184 system folders |

**Purpose:** Designated testing-only drive for HyperSpin Toolkit development. This drive has known issues making it unsuitable for active gaming but perfect for safe, non-destructive testing of toolkit features (M12–M15 update pipeline, rollback, snapshot verification, etc.).

**Top-Level Structure:**
```
D:\
├── Arcade\                    (184 system folders)
├── BACKUP FILES - HYPERSPIN & ROCKETLAUNCHER\
├── Buttons to use to Exit Systems from Hyperspin\
├── CLI-Anything\
├── HyperSpin_Backups\
├── HyperSpin_Recovery\
├── hyperspin_toolkit\         (this project)
├── HyperSpin_Toolkit_Output\
└── SETUP USER GUIDE - FOR HYPERSPIN\
```

---

### 🟢 I: — PRIMARY_HYPERSPIN (Active Gaming)

| Property | Value |
|----------|-------|
| **Tag** | `PRIMARY_HYPERSPIN` |
| **Physical Disk** | Disk 7 |
| **Model** | Seagate ST12000N M000J-2TY103 |
| **Serial** | `00000000471D` (USB enclosure — identify by model) |
| **Capacity** | 11,176 GB (12TB) |
| **Free Space** | 55 GB (0.5%) |
| **Filesystem** | NTFS |
| **Health** | ✅ Healthy |
| **Collection** | HyperSpin + RocketLauncher |
| **Systems** | 184 system folders (identical to D:) |

**Purpose:** Active primary HyperSpin gaming drive. Identical clone of D:. This is the one used for actual gaming sessions.

---

### 🟢 K: — HYPERSPIN_ATTRACTION (Backup)

| Property | Value |
|----------|-------|
| **Tag** | `HYPERSPIN_ATTRACTION` |
| **Physical Disk** | Disk 6 |
| **Model** | HGST HUH72121 2ALE601 |
| **Serial** | `00000000471D` (USB enclosure — identify by model) |
| **Capacity** | 11,176 GB (12TB) |
| **Free Space** | 178 GB (1.6%) |
| **Filesystem** | NTFS |
| **Health** | ✅ Healthy |
| **Collection** | HyperSpin Attract Mode |
| **Collections** | 199 |
| **Emulators** | 55 |

**Purpose:** HyperSpin Attraction/Attract Mode setup. Backup drive — not used for active gaming. Different organizational structure from D:/I: (collections + emulators under Arcade/ instead of per-system ROM folders).

**Top-Level Structure:**
```
K:\
├── 2025_Downloads\
├── AI\
├── AI3\
├── Arcade\
│   ├── collections\           (199 collection folders)
│   ├── emulators\             (55 emulators)
│   ├── layouts\
│   ├── plugins\
│   └── ...
├── Help_faqs\
├── PP4_Maps_V 2.2.0\
└── Schedules\
```

---

### 🟡 L: — CORE_TYPE_R (User Favorite)

| Property | Value |
|----------|-------|
| **Tag** | `CORE_TYPE_R` |
| **Physical Disk** | Disk 9 |
| **Model** | HGST HUH72121 2ALE601 |
| **Serial** | `558638EE1A62` |
| **Capacity** | 11,176 GB (12TB) |
| **Free Space** | 161 GB (1.4%) |
| **Filesystem** | NTFS |
| **Health** | ⚠ **Warning** — filesystem issues detected |
| **Collection** | CORE - TYPE R (LaunchBox/RetroArch-style) |
| **Backup** | → H: Retro_14tb (14TB, empty, ready for HDD clone) |

**Purpose:** User favorite collection. LaunchBox/RetroArch-style "CORE - TYPE R" with collections, core, launchers, layouts, and meta structure. **Priority backup target** — clone to H: using HDD cloner.

**Top-Level Structure:**
```
L:\
├── [=]_torrents_2024_[=]\
├── CORE - TYPE R\
│   ├── collections\           (5 top-level: _common, COMPUTERS, Main, SETTINGS, SETTINGS TITAN)
│   ├── core\
│   ├── emulators\
│   ├── launchers.windows\
│   ├── layouts\
│   ├── meta\
│   └── settings\
├── GTA5\
├── help_faqs\
├── Installation\
├── SaveData\
└── Schedules\
```

---

### 🟢 H: — BACKUP_14TB (Empty — Backup Target)

| Property | Value |
|----------|-------|
| **Tag** | `BACKUP_14TB` |
| **Physical Disk** | Disk 5 |
| **Model** | WDC WUH 721414ALE6L1 |
| **Capacity** | 13,039 GB (14TB) |
| **Free Space** | 13,039 GB (100% — empty) |
| **Filesystem** | exFAT |
| **Health** | ✅ Healthy |

**Purpose:** Empty 14TB drive designated as the low-level clone backup for L: (CORE - TYPE R). User has an HDD cloner for this operation.

---

### 🟢 J: — ROM_BACKUP_20TB

| Property | Value |
|----------|-------|
| **Tag** | `ROM_BACKUP_20TB` |
| **Physical Disk** | Disk 8 |
| **Model** | OOS20000 G (20TB) |
| **Capacity** | 18,627 GB (20TB) |
| **Free Space** | 67 GB (0.4%) |
| **Filesystem** | exFAT |
| **Health** | ✅ Healthy |
| **Backup** | Needs 22TB drive (not yet acquired) |

**Purpose:** Backup HDD with game ROMs (Switch, PC games like GTA5, Cyberpunk 2077, RDR2, Flight Simulator, etc.), downloads, and tools. NOT an active gaming collection. Switch games here could be added to whichever active drive has capacity + the proper emulator (e.g., Yuzu/Ryujinx) if ROMs are in compatible format (.nsp, .xci).

---

### 🟢 E: — ARCHIVE_4TB

| Property | Value |
|----------|-------|
| **Tag** | `ARCHIVE_4TB` |
| **Physical Disk** | Disk 4 |
| **Model** | Seagate Game Drive PS4 |
| **Serial** | `NZ0DENDR` |
| **Capacity** | 3,726 GB (4TB) |
| **Free Space** | 2,563 GB (69%) |
| **Filesystem** | exFAT |
| **Health** | ✅ Healthy |

**Purpose:** Archive drive with AI models (LM Studio at `.lmstudio/`, Ollama at `.ollama/`), Windsurf data, software ISOs, Android APKs, and project files.

---

### 🟡 M: + N: — BATOCERA (Boot + Games)

**M: Boot Partition:**
| Property | Value |
|----------|-------|
| **Capacity** | 7 GB (FAT32) |
| **Health** | ✅ Healthy |

**N: Game Data Partition:**
| Property | Value |
|----------|-------|
| **Tag** | `BATOCERA_GAMES` |
| **Capacity** | 1,856 GB (~2TB) |
| **Free Space** | 20 GB (1%) |
| **Filesystem** | NTFS |
| **Health** | ⚠ **Warning** |
| **Systems** | 219 ROM system folders |

**Purpose:** Batocera Linux retro-gaming OS. M: is the boot partition, N: holds all game data (ROMs for 219 systems, BIOS files, themes, cheats, saves, decorations). Both partitions are on a single physical disk (Disk 10, JMicron Generic, ~2TB total).

---

## Collection Type Classification

### Type 1: HyperSpin + RocketLauncher
- **Drives:** D: (testing), I: (active)
- **Structure:** `Arcade/{SystemName}/` with per-system ROM folders
- **Frontend:** HyperSpin.exe
- **Backend:** RocketLauncher
- **Systems:** 184
- **Identifier:** Presence of `Arcade/` with system-named subfolders + `BACKUP FILES - HYPERSPIN & ROCKETLAUNCHER/`

### Type 2: HyperSpin Attract Mode
- **Drives:** K: (backup)
- **Structure:** `Arcade/collections/`, `Arcade/emulators/`, `Arcade/layouts/`
- **Frontend:** HyperSpin Attraction variant
- **Collections:** 199
- **Emulators:** 55
- **Identifier:** Presence of `Arcade/collections/` and `Arcade/emulators/`

### Type 3: CORE - TYPE R (LaunchBox/RetroArch)
- **Drives:** L: (active)
- **Structure:** `CORE - TYPE R/{collections,core,launchers.windows,layouts,meta,settings}/`
- **Frontend:** LaunchBox/BigBox-style
- **Identifier:** Presence of `CORE - TYPE R/` directory

### Type 4: Batocera
- **Drives:** M: (boot) + N: (games)
- **Structure:** `roms/{system}/`, `bios/`, `themes/`, `saves/`
- **Frontend:** Batocera Linux (EmulationStation)
- **Systems:** 219
- **Identifier:** Presence of `roms/`, `bios/`, `themes/`, `decorations/`

### Type 5: ROM Backup / PC Games
- **Drives:** J:
- **Structure:** Mixed — game folders, download folders, torrent archives
- **Not a frontend collection** — raw storage/backup
- **Identifier:** Presence of `Games/`, `[=]_*` bracket-named folders

---

## Backup Strategy

### Immediate Priority (Has Backup Target)
| Source | Target | Method | Status |
|--------|--------|--------|--------|
| L: CORE - TYPE R (12TB) | H: Retro_14tb (14TB) | HDD Cloner (low-level) | ⏳ Pending |

### Needs Backup Drive Acquired
| Source | Needed Backup Size | Status |
|--------|-------------------|--------|
| J: 20_TB | 22TB+ | ❌ Not acquired |

### Already Has Clone/Backup
| Primary | Backup/Clone | Notes |
|---------|-------------|-------|
| I: Hyperspin_12T | D: Hyperspin_12T | D: has issues → testing only |

### No Backup Yet
| Drive | Size | Priority |
|-------|------|----------|
| K: HyperSpin Attraction | 12TB | Medium |
| N: Batocera Games | 2TB | Medium (Warning health) |
| E: Archive2023 | 4TB | Low (69% free) |

### Upgrade Path (12TB → 14-22TB)
All 12TB drives should eventually be upgraded to larger sizes (14TB–22TB) to accommodate growth:
- D: 12TB → 14-18TB (testing)
- I: 12TB → 14-18TB (primary HyperSpin)
- K: 12TB → 14-18TB (attraction mode)
- L: 12TB → 14-18TB (CORE - TYPE R)
- Goal: Always have backup drives 2TB larger than source for upgrade headroom.

---

## Drive Identification When Drive Letters Change

Since many USB drives share the generic serial `00000000471D`, use this identification strategy:

1. **Primary:** Match `serial` from `drive_registry.json`
2. **Fallback:** Match `model` + `capacity_gb` combo
3. **Verification:** Check top-level directory structure against `collection_types` identifiers

The toolkit's `engines/auto_rollback.py` and future M31 (Multi-Drive Collection Sync) should use `drive_registry.json` for drive identification.

### Unique Serials (Reliable)
| Serial | Drive |
|--------|-------|
| `7E0538EE1A62` | D: TEST_HYPERSPIN (Seagate 12TB) |
| `558638EE1A62` | L: CORE_TYPE_R (HGST 12TB) |
| `NZ0DENDR` | E: ARCHIVE_4TB (Seagate 4TB) |
| `0123456789ABCDEF` | M:+N: BATOCERA (JMicron 2TB) |

### Generic Serials (Use Model+Size)
| Model | Size | Drive |
|-------|------|-------|
| ST12000N M000J-2TY103 | 11176 GB | I: PRIMARY_HYPERSPIN |
| HUH72121 2ALE601 | 11176 GB | K: HYPERSPIN_ATTRACTION |
| WDC WUH 721414ALE6L1 | 13039 GB | H: BACKUP_14TB |
| OOS20000 G | 18627 GB | J: ROM_BACKUP_20TB |
