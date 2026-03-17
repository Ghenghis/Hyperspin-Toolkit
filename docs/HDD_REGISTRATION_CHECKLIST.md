# HDD Registration Checklist

> **Do this today — plug in each HDD one at a time and complete its section below.**
> After each drive is registered, its letter/role/label is saved to `drives.json` permanently.

---

## Before You Start

```powershell
# From D:\hyperspin_toolkit — run once to see what's currently known
python main.py drives status
python main.py drives scan
```

Note down the output so you know what's already registered.

---

## Drive Registration Template

For each HDD you plug in, copy and fill out this block:

```
Drive Label:    ________________________________  (e.g. ARCADE_10TB, GAMES_20TB)
Physical Size:  ________________________________  (e.g. 10TB, 12TB, 20TB)
Contents:       ________________________________  (e.g. HyperSpin, ROMs, Emulators, Media)
Assigned Role:  ________________________________  (primary / secondary / tertiary / none)
Drive Letter:   ________________________________  (assigned by Windows when plugged in)
Root Folder:    ________________________________  (e.g. Arcade, Games, or just the drive root)
Registration:   [ ] Done    Date: _______________
```

---

## Step-by-Step for Each HDD

### Step 1 — Plug in the HDD
- Connect via USB / SATA dock
- Wait for Windows to assign a drive letter
- Note the letter Windows assigned (check File Explorer)

### Step 2 — Scan to confirm detection
```powershell
python main.py drives scan
```
Find your drive in the list. Note:
- The letter it was assigned
- What content was detected (HyperSpin / ROMs / Emulators etc.)

### Step 3 — Assign a role
```powershell
# If this is your MAIN arcade drive (HyperSpin + all emulators + primary ROMs):
python main.py drives set primary <LETTER>

# If this is an OVERFLOW drive (extra ROMs, additional games, second system):
python main.py drives set secondary <LETTER>

# If this is a TERTIARY drive (extras, media, backups, third collection):
python main.py drives set tertiary <LETTER>
```

> **Only one drive can hold each role.** If you re-assign a role, the old one is replaced.

### Step 4 — Verify it saved
```powershell
python main.py drives status
```
Confirm the drive shows up under the correct role with the right path.

### Step 5 — Check drive health (optional but recommended)
```powershell
python main.py drives health <LETTER>
```
Confirm SMART status PASSED before trusting the drive with important data.

### Step 6 — Mark as done in the table below

---

## Drive Inventory Table

Fill this in as you register each drive. Update `[ ]` to `[x]` when done.

| # | Label | Size | Letter | Role | Root Path | Contents | Health | Done |
|---|-------|------|--------|------|-----------|----------|--------|------|
| 1 | | | | primary | | | | [ ] |
| 2 | | | | secondary | | | | [ ] |
| 3 | | | | tertiary | | | | [ ] |
| 4 | | | | none | | | | [ ] |
| 5 | | | | none | | | | [ ] |
| 6 | | | | none | | | | [ ] |

---

## After All Drives Are Registered

```powershell
# 1. Confirm final state
python main.py drives status

# 2. Run a full audit now that all paths are known
python main.py audit full

# 3. If any drive letter will change when reconnected later, document it here:
```

### Drive Letter Notes
> Windows assigns drive letters based on connection order. If letters change next time:
> ```powershell
> python main.py drives scan        # See new letters
> python main.py drives auto        # Auto-reassign roles to detected drives
> # OR manually:
> python main.py drives set primary <NEW_LETTER>
> ```

---

## Transfer / Migration Plans

If you want to move a collection from a smaller drive to a larger one, fill this in:

| From | To | Content | Plan | Status |
|------|----|---------|------|--------|
| | | | `drives migrate` | [ ] planned |
| | | | `drives migrate` | [ ] planned |

```powershell
# Space check before committing:
python main.py drives plan "<SOURCE_ROOT>" <DEST_LETTER>

# Preview (no files copied):
python main.py drives migrate "<SOURCE>" "<DEST>" --dry-run

# Execute:
python main.py drives migrate "<SOURCE>" "<DEST>" --verify
```

---

## Completed Registrations

> Update this section as you finish each drive today.

- [ ] Drive 1 registered
- [ ] Drive 2 registered
- [ ] Drive 3 registered
- [ ] Drive 4 registered
- [ ] All drives in `drives status` look correct
- [ ] Full audit run after all drives registered
- [ ] Transfer plans noted (if any drives need migrating)
