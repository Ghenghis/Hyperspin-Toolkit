# Backup Strategy & Drive Upgrade Plan

> **Last Updated:** 2026-03-17  
> **Registry:** `drive_registry.json`

---

## Current Backup Status

| Drive | Size | Has Backup? | Backup Target | Method | Status |
|-------|------|-------------|---------------|--------|--------|
| I: Primary HyperSpin | 12TB | ✅ D: is clone | D: (12TB, Warning) | Previous clone | Clone has issues |
| L: CORE - TYPE R | 12TB | ⏳ Pending | H: Retro_14tb (14TB) | HDD Cloner (low-level) | **Priority #1** |
| K: HyperSpin Attraction | 12TB | ❌ None | Need 14-18TB | TBD | Not started |
| J: ROM Backup 20TB | 20TB | ❌ None | Need 22TB+ | TBD | Drive not acquired |
| N: Batocera Games | 2TB | ❌ None | Need 4TB | TBD | Not started |
| E: Archive2023 | 4TB | ❌ None | Low priority (69% free) | TBD | Not started |

---

## Priority 1: Clone L: → H:

**Source:** L: Super Game HDD (CORE - TYPE R) — 11,176 GB, ⚠ Warning health  
**Target:** H: Retro_14tb — 13,039 GB, empty, exFAT, ✅ Healthy

### Pre-Clone Checklist
- [ ] Run `chkdsk L: /f /r /x` to fix any filesystem errors before cloning
- [ ] Capture snapshot: `python main.py snapshots capture "L:\CORE - TYPE R" --name "core-type-r-pre-clone"`
- [ ] Note L: serial (`558638EE1A62`) and H: model (`WDC WUH 721414ALE6L1`)
- [ ] Verify H: is truly empty (format if needed)

### Clone Procedure
1. **Disconnect all non-essential USB drives** to avoid accidental cloning to wrong drive
2. Connect L: (source) and H: (target) to HDD cloner
3. Select **low-level sector clone** (preserves NTFS structure exactly)
4. Start clone — estimated time: 8-12 hours for 11TB of data
5. **Do NOT interrupt** — power loss during clone corrupts target

### Post-Clone Verification
- [ ] Connect H: clone to PC
- [ ] Run `python main.py snapshots capture "H:\CORE - TYPE R" --name "core-type-r-clone"`
- [ ] Run `python main.py snapshots compare "core-type-r-pre-clone" "core-type-r-clone"`
- [ ] Verify 0 differences (or only expected timestamp changes)
- [ ] Run `chkdsk H: /f` to verify filesystem integrity on clone
- [ ] Update `drive_registry.json` — mark H: as backup of L:

### Important Notes
- H: is exFAT but low-level clone will overwrite with L:'s NTFS filesystem
- After clone, H: label will change to "Super Game HDD" (matching L:)
- Relabel H: to `CORE_TYPE_R_BACKUP` after clone verification
- Store H: safely — this is the only backup of user's favorite collection

---

## Priority 2: Acquire 22TB for J: Backup

**Source:** J: 20_TB — 18,627 GB, exFAT  
**Target:** Need 22TB+ drive

### Recommended Drives (22TB Class)
| Model | Capacity | Interface | Est. Price | Notes |
|-------|----------|-----------|-----------|-------|
| WD Red Pro 22TB (WD221KFGX) | 22TB | SATA/USB | ~$400 | NAS-rated, 5-yr warranty |
| Seagate IronWolf Pro 22TB (ST22000NT001) | 22TB | SATA/USB | ~$380 | NAS-rated, 5-yr warranty |
| WD Ultrastar HC580 24TB | 24TB | SATA/USB | ~$450 | Enterprise, most headroom |
| Seagate Exos X24 24TB | 24TB | SATA/USB | ~$440 | Enterprise, 5-yr warranty |

### Why 22TB+
- J: is 18,627 GB used → need minimum 20TB backup
- **2TB upgrade headroom rule** → 22TB minimum
- 24TB provides more future growth space

---

## Priority 3: Batocera Backup (N:)

**Source:** N: Batocera Games — 1,856 GB, NTFS, ⚠ Warning  
**Target:** Any 4TB+ drive (or partition on existing drive)

### Options
1. **Use existing free space on E: Archive2023** (2,563 GB free) — create backup folder
2. **Use partition on G: SSD** (1,009 GB free) — fast but SSD wear concern
3. **Acquire dedicated 4TB external** — cleanest option (~$80)

### Recommendation
Option 1 is cheapest — back up N:\roms to E:\Batocera_Backup\ as a file-level copy. This protects the 219-system ROM collection while N: has Warning health.

```powershell
# Quick file-level backup of Batocera ROMs
robocopy N:\ E:\Batocera_Backup\ /MIR /MT:8 /R:3 /W:5 /LOG:batocera_backup.log
```

---

## Drive Upgrade Path

### Sizing Rule
> **Always buy backup/upgrade drives 2TB larger than the source** to accommodate growth.

| Current Size | Upgrade Range | Purpose |
|-------------|---------------|---------|
| 12TB | 14–18TB | All four 12TB drives (D:, I:, K:, L:) |
| 20TB | 22–24TB | J: backup |
| 2TB | 4TB | N: Batocera backup |

### Upgrade Procedure (Per Drive)

1. **Pre-upgrade snapshot** of source drive
2. **Acquire new larger drive**
3. **Low-level clone** source → new drive via HDD cloner
4. **Verify clone** using snapshot comparison
5. **Update drive_registry.json** with new serial, model, capacity
6. **Relabel** new drive appropriately
7. **Physical label** the enclosure
8. **Repurpose or retire** the old drive
   - Old healthy drives → secondary backups or donation
   - Old Warning drives → recycle (do NOT trust for data storage)

### Budget Estimate
| Item | Qty | Unit Price | Total |
|------|-----|-----------|-------|
| 14TB WD/Seagate (for 12TB upgrades) | 4 | ~$220 | ~$880 |
| 22TB WD/Seagate (for J: backup) | 1 | ~$400 | ~$400 |
| 4TB external (for N: backup) | 1 | ~$80 | ~$80 |
| USB 3.0+ enclosures (if needed) | 2 | ~$30 | ~$60 |
| **Total estimate** | | | **~$1,420** |

---

## Filesystem Health Remediation

Three drives show Warning status. Address before any critical operations:

### D: Test_Hyperspin_Test (Will become testing drive)
```powershell
# Schedule CHKDSK (may require reboot if volume is locked)
chkdsk D: /f /r /x
```
- Low priority — this drive has known issues and is testing-only
- CHKDSK results will document the extent of filesystem damage
- May find bad sectors, orphaned files, or index corruption

### L: Super Game HDD / CORE - TYPE R
```powershell
chkdsk L: /f /r /x
```
- **HIGH priority** — clone to H: first, THEN run CHKDSK
- Running CHKDSK on a damaged drive without backup risks further data loss
- Clone preserves current state regardless of filesystem errors

### N: Batocera Games
```powershell
chkdsk N: /f /r /x
```
- Medium priority — back up to E: first (robocopy), then CHKDSK
- Batocera partitions on JMicron enclosures are prone to dirty bit issues

---

## Automated Backup Monitoring

Once M23 (Health Dashboard) and M34 (Ecosystem Health Score) are implemented:

- **Drive health polling** every 4 hours via scheduled task
- **Warning alerts** via WebSocket Event Hub (M22) when:
  - Volume health degrades from Healthy to Warning
  - Free space drops below 2% on any gaming drive
  - Backup age exceeds 30 days
- **Backup verification** after every clone/sync operation using M14 snapshots
- **Drive identity check** at startup using `drive_registry.json` serials
