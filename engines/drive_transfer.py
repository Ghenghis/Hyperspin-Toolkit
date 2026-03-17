"""Drive Transfer Engine — migrate arcade collection between HDDs.

Handles:
  - Smart copy with progress tracking (speed, ETA, file count)
  - Skip-already-transferred files (resume interrupted transfers)
  - Post-transfer hash verification
  - Automatic path rewrite in all RocketLauncher INI files after move
  - Selective transfer (ROMs only, emulators only, media only, etc.)
  - Space pre-check before starting
  - Dry-run mode
  - Transfer manifest saved for resume/verification
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterator, Optional

# ── Transfer categories ─────────────────────────────────────────────
CATEGORIES = {
    "roms":        ["ROMs"],
    "emulators":   ["emulators"],
    "media":       ["HyperSpin\\Media", "Media"],
    "hyperspin":   ["HyperSpin"],
    "rocketlauncher": ["RocketLauncher"],
    "databases":   ["Databases", "HyperSpin\\Databases"],
    "settings":    ["Settings", "HyperSpin\\Settings"],
    "all":         [],  # empty = entire arcade root
}

MANIFEST_NAME = ".hstk_transfer_manifest.json"


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class TransferFile:
    src:         str
    dst:         str
    size:        int
    status:      str = "pending"   # pending / copied / skipped / failed / verified
    src_hash:    str = ""
    dst_hash:    str = ""
    error:       str = ""


@dataclass
class TransferPlan:
    source_root:  str
    dest_root:    str
    categories:   list[str]
    total_files:  int   = 0
    total_bytes:  int   = 0
    files:        list[TransferFile] = field(default_factory=list)
    created_at:   str   = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TransferPlan":
        files = [TransferFile(**f) for f in d.pop("files", [])]
        p = cls(**d)
        p.files = files
        return p


@dataclass
class TransferResult:
    copied:       int = 0
    skipped:      int = 0
    failed:       int = 0
    verified_ok:  int = 0
    verified_fail: int = 0
    bytes_copied: int = 0
    elapsed_sec:  float = 0.0
    errors:       list[str] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────

def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _speed(bps: float) -> str:
    return _human(int(bps)) + "/s"


def _file_hash(path: str, algo: str = "xxhash") -> str:
    """Fast hash — uses xxhash if available, falls back to md5."""
    try:
        import xxhash
        h = xxhash.xxh64()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()
    except ImportError:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()


def _iter_files(root: Path) -> Iterator[Path]:
    """Walk root recursively, yield all files."""
    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            yield Path(dirpath) / fname


def _manifest_path(dest_root: Path) -> Path:
    return dest_root / MANIFEST_NAME


# ── Space planning ───────────────────────────────────────────────────

def plan_space(
    source_root: str,
    dest_drive:  str,
    categories:  list[str] | None = None,
) -> dict:
    """
    Calculate how much space is needed vs available.

    Returns:
        needed_bytes, available_bytes, fits, category_breakdown
    """
    src = Path(source_root)
    dest_letter = str(dest_drive).upper().strip(":\\")
    dest_drive_path = Path(f"{dest_letter}:\\")

    cats = categories or ["all"]
    breakdown: dict[str, dict] = {}
    total_bytes = 0

    for cat in cats:
        subdirs = CATEGORIES.get(cat, [])
        cat_bytes = 0
        cat_files = 0

        if not subdirs:
            for f in _iter_files(src):
                size = f.stat().st_size
                cat_bytes += size
                cat_files += 1
        else:
            for subdir in subdirs:
                sub = src / subdir
                if sub.exists():
                    for f in _iter_files(sub):
                        size = f.stat().st_size
                        cat_bytes += size
                        cat_files += 1

        breakdown[cat] = {
            "bytes": cat_bytes,
            "files": cat_files,
            "human": _human(cat_bytes),
        }
        total_bytes += cat_bytes

    try:
        usage = shutil.disk_usage(str(dest_drive_path))
        available = usage.free
    except Exception:
        available = 0

    return {
        "source_root":     source_root,
        "dest_drive":      dest_letter,
        "needed_bytes":    total_bytes,
        "needed_human":    _human(total_bytes),
        "available_bytes": available,
        "available_human": _human(available),
        "fits":            total_bytes <= available,
        "margin_bytes":    available - total_bytes,
        "margin_human":    _human(max(0, available - total_bytes)),
        "categories":      breakdown,
    }


# ── Transfer plan builder ────────────────────────────────────────────

def build_plan(
    source_root: str,
    dest_root:   str,
    categories:  list[str] | None = None,
    verify:      bool = False,
) -> TransferPlan:
    """
    Build a TransferPlan listing every file to copy from source to dest.
    Loads existing manifest from dest to mark already-completed files as skipped.
    """
    import datetime

    cats  = categories or ["all"]
    src   = Path(source_root)
    dst   = Path(dest_root)

    # Load existing manifest for resume
    existing: dict[str, str] = {}   # dst_path → status
    manifest_file = _manifest_path(dst)
    if manifest_file.exists():
        try:
            prev = TransferPlan.from_dict(
                json.loads(manifest_file.read_text(encoding="utf-8"))
            )
            for tf in prev.files:
                if tf.status in ("copied", "verified"):
                    existing[tf.dst] = tf.status
        except Exception:
            pass

    plan = TransferPlan(
        source_root=source_root,
        dest_root=dest_root,
        categories=cats,
        created_at=datetime.datetime.now().isoformat(),
    )

    def _add_dir(subdir_path: Path) -> None:
        if not subdir_path.exists():
            return
        for src_file in _iter_files(subdir_path):
            rel = src_file.relative_to(src)
            dst_file = dst / rel
            status = existing.get(str(dst_file), "pending")
            tf = TransferFile(
                src=str(src_file),
                dst=str(dst_file),
                size=src_file.stat().st_size,
                status=status,
            )
            plan.files.append(tf)
            plan.total_bytes += tf.size
            plan.total_files += 1

    for cat in cats:
        subdirs = CATEGORIES.get(cat, [])
        if not subdirs:
            _add_dir(src)
        else:
            for subdir in subdirs:
                _add_dir(src / subdir)

    return plan


def _save_manifest(plan: TransferPlan, dest_root: str) -> None:
    p = _manifest_path(Path(dest_root))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")


# ── Transfer executor ────────────────────────────────────────────────

def execute_transfer(
    plan:        TransferPlan,
    verify:      bool = False,
    dry_run:     bool = False,
    progress_cb: Optional[Callable[[dict], None]] = None,
) -> TransferResult:
    """
    Execute a TransferPlan. Copies files, optionally verifies hashes.

    progress_cb(state) is called after each file with:
      {files_done, files_total, bytes_done, bytes_total,
       current_file, speed_bps, eta_sec, pct}
    """
    result = TransferResult()
    start  = time.monotonic()
    bytes_done = 0
    files_done = 0
    files_total = sum(1 for f in plan.files if f.status == "pending")
    bytes_total = sum(f.size for f in plan.files if f.status == "pending")

    for tf in plan.files:
        if tf.status in ("copied", "verified", "skipped"):
            result.skipped += 1
            continue

        # Check dest already exists with correct size
        dst_path = Path(tf.dst)
        if dst_path.exists() and dst_path.stat().st_size == tf.size:
            tf.status = "skipped"
            result.skipped += 1
            continue

        if dry_run:
            tf.status = "pending"
            files_done += 1
            bytes_done += tf.size
            continue

        try:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.monotonic()
            shutil.copy2(tf.src, tf.dst)
            elapsed = time.monotonic() - t0
            tf.status = "copied"
            result.copied += 1
            result.bytes_copied += tf.size
        except Exception as exc:
            tf.status = "failed"
            tf.error = str(exc)
            result.failed += 1
            result.errors.append(f"{tf.src}: {exc}")

        files_done += 1
        bytes_done += tf.size

        if progress_cb:
            elapsed_total = time.monotonic() - start
            speed = bytes_done / elapsed_total if elapsed_total > 0 else 0
            remaining = bytes_total - bytes_done
            eta = remaining / speed if speed > 0 else 0
            progress_cb({
                "files_done":   files_done,
                "files_total":  files_total,
                "bytes_done":   bytes_done,
                "bytes_total":  bytes_total,
                "bytes_done_human":  _human(bytes_done),
                "bytes_total_human": _human(bytes_total),
                "current_file": tf.src,
                "speed_bps":    speed,
                "speed_human":  _speed(speed),
                "eta_sec":      int(eta),
                "pct":          round(bytes_done / bytes_total * 100, 1) if bytes_total > 0 else 0,
            })

        # Save manifest every 500 files
        if files_done % 500 == 0:
            _save_manifest(plan, plan.dest_root)

    # Final manifest save
    if not dry_run:
        _save_manifest(plan, plan.dest_root)

    # Verify phase
    if verify and not dry_run:
        for tf in plan.files:
            if tf.status != "copied":
                continue
            try:
                tf.src_hash = _file_hash(tf.src)
                tf.dst_hash = _file_hash(tf.dst)
                if tf.src_hash == tf.dst_hash:
                    tf.status = "verified"
                    result.verified_ok += 1
                else:
                    tf.status = "failed"
                    tf.error = "hash mismatch"
                    result.verified_fail += 1
                    result.errors.append(f"HASH MISMATCH: {tf.dst}")
            except Exception as exc:
                tf.status = "failed"
                tf.error = str(exc)
                result.verified_fail += 1

        _save_manifest(plan, plan.dest_root)

    result.elapsed_sec = time.monotonic() - start
    return result


# ── INI path rewriter ─────────────────────────────────────────────────

def rewrite_ini_paths(
    ini_root:    str,
    old_letter:  str,
    new_letter:  str,
    dry_run:     bool = False,
) -> dict:
    """
    Scan all .ini files under ini_root and replace every occurrence of
    old_letter:\\ with new_letter:\\.

    Returns: {files_scanned, files_changed, lines_changed}
    """
    old_letter = old_letter.upper().strip(":\\")
    new_letter = new_letter.upper().strip(":\\")
    old_prefix = f"{old_letter}:\\"
    new_prefix = f"{new_letter}:\\"

    files_scanned  = 0
    files_changed  = 0
    lines_changed  = 0
    changed_files:  list[str] = []

    for dirpath, _, filenames in os.walk(ini_root):
        for fname in filenames:
            if not fname.lower().endswith(".ini"):
                continue
            fpath = Path(dirpath) / fname
            files_scanned += 1
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                new_content = content.replace(old_prefix, new_prefix)
                if new_content != content:
                    n = content.count(old_prefix)
                    lines_changed += n
                    files_changed += 1
                    changed_files.append(str(fpath))
                    if not dry_run:
                        fpath.write_text(new_content, encoding="utf-8")
            except Exception:
                pass

    return {
        "files_scanned": files_scanned,
        "files_changed": files_changed,
        "lines_changed": lines_changed,
        "changed_files": changed_files[:50],
        "dry_run":       dry_run,
    }


# ── SMART / drive health ──────────────────────────────────────────────

def drive_health_check(letter: str) -> dict:
    """
    Check HDD/SSD health using wmic (built-in Windows) and smartctl if available.
    Returns a health summary with status, temperature, reallocated sectors etc.
    """
    import subprocess
    letter = str(letter).upper().strip(":\\")
    result: dict = {"letter": letter, "available": False, "smart": {}, "wmic": {}}

    # WMIC physical disk info (always available on Windows)
    try:
        r = subprocess.run(
            ["wmic", "diskdrive", "get",
             "Status,MediaType,Size,Caption,InterfaceType,SerialNumber",
             "/format:csv"],
            capture_output=True, text=True, timeout=10, shell=True
        )
        for line in r.stdout.splitlines():
            if line.strip() and "," in line:
                parts = line.strip().split(",")
                if len(parts) >= 5 and parts[1].strip():
                    result["wmic"] = {
                        "caption":   parts[1].strip(),
                        "interface": parts[2].strip(),
                        "media":     parts[3].strip(),
                        "serial":    parts[4].strip() if len(parts) > 4 else "",
                        "size":      parts[5].strip() if len(parts) > 5 else "",
                        "status":    parts[6].strip() if len(parts) > 6 else "Unknown",
                    }
                    result["available"] = True
                    break
    except Exception:
        pass

    # smartctl (if installed — from smartmontools)
    try:
        r = subprocess.run(
            ["smartctl", "-H", "-A", f"{letter}:"],
            capture_output=True, text=True, timeout=15
        )
        smart = {"raw": r.stdout[:2000]}
        for line in r.stdout.splitlines():
            if "SMART overall-health" in line:
                smart["health"] = "PASSED" if "PASSED" in line else "FAILED"
            if "Reallocated_Sector_Ct" in line:
                parts = line.split()
                smart["reallocated_sectors"] = parts[-1] if parts else "?"
            if "Temperature_Celsius" in line or "Airflow_Temperature" in line:
                parts = line.split()
                smart["temperature_c"] = parts[-1] if parts else "?"
            if "Power_On_Hours" in line:
                parts = line.split()
                smart["power_on_hours"] = parts[-1] if parts else "?"
        result["smart"] = smart
        result["available"] = True
    except FileNotFoundError:
        result["smart"]["note"] = "smartctl not installed (optional: https://www.smartmontools.org)"
    except Exception as exc:
        result["smart"]["error"] = str(exc)

    # Basic connectivity
    result["connected"] = os.path.exists(f"{letter}:\\")
    if result["connected"]:
        try:
            usage = shutil.disk_usage(f"{letter}:\\")
            result["total_gb"] = round(usage.total / (1024**3), 1)
            result["free_gb"]  = round(usage.free  / (1024**3), 1)
            result["used_pct"] = round(usage.used  / usage.total * 100, 1)
        except Exception:
            pass

    return result


# ── Summary helper ───────────────────────────────────────────────────

# ── Drive comparison ─────────────────────────────────────────────────

def compare_drives(
    source_root: str,
    dest_root:   str,
    check_size:  bool = True,
) -> dict:
    """
    Compare two directory trees and report:
      - Files only in source (not yet copied / missing on dest)
      - Files only in dest   (extra / orphaned on dest)
      - Size mismatches      (file exists on both but differs in size)

    Returns a summary dict with lists capped at 200 items each.
    """
    src = Path(source_root)
    dst = Path(dest_root)

    src_files: dict[str, int] = {}   # rel_path → size
    dst_files: dict[str, int] = {}

    for f in _iter_files(src):
        try:
            src_files[str(f.relative_to(src))] = f.stat().st_size
        except Exception:
            pass

    for f in _iter_files(dst):
        try:
            dst_files[str(f.relative_to(dst))] = f.stat().st_size
        except Exception:
            pass

    src_set = set(src_files)
    dst_set = set(dst_files)

    only_in_src  = sorted(src_set - dst_set)
    only_in_dst  = sorted(dst_set - src_set)
    size_mismatch: list[dict] = []

    if check_size:
        for rel in src_set & dst_set:
            if src_files[rel] != dst_files[rel]:
                size_mismatch.append({
                    "path":     rel,
                    "src_size": src_files[rel],
                    "dst_size": dst_files[rel],
                })

    only_in_src_bytes = sum(src_files[p] for p in only_in_src)
    mismatch_bytes    = sum(src_files[m["path"]] for m in size_mismatch)

    return {
        "source_root":        source_root,
        "dest_root":          dest_root,
        "source_total_files": len(src_files),
        "dest_total_files":   len(dst_files),
        "only_in_source":      only_in_src[:200],
        "only_in_source_count": len(only_in_src),
        "only_in_source_bytes": only_in_src_bytes,
        "only_in_source_human": _human(only_in_src_bytes),
        "only_in_dest":        only_in_dst[:200],
        "only_in_dest_count":  len(only_in_dst),
        "size_mismatches":     size_mismatch[:200],
        "size_mismatch_count": len(size_mismatch),
        "size_mismatch_bytes": mismatch_bytes,
        "size_mismatch_human": _human(mismatch_bytes),
        "in_sync":            len(only_in_src) == 0 and len(size_mismatch) == 0,
    }


# ── Drive sync (incremental mirror) ──────────────────────────────────

def sync_drives(
    source_root: str,
    dest_root:   str,
    delete_extra: bool = False,
    verify:       bool = False,
    dry_run:      bool = False,
    progress_cb:  Optional[Callable[[dict], None]] = None,
) -> TransferResult:
    """
    Incremental sync: copy everything from source to dest that is missing or
    has a different size. Optionally delete files on dest that no longer exist
    in source (mirror mode).

    This is the 'keep secondary drive current' operation.
    """
    src = Path(source_root)
    dst = Path(dest_root)

    result = TransferResult()
    start  = time.monotonic()
    files_done  = 0
    bytes_done  = 0

    # Collect dest state
    dst_index: dict[str, int] = {}
    for f in _iter_files(dst):
        try:
            dst_index[str(f.relative_to(dst))] = f.stat().st_size
        except Exception:
            pass

    # Build work list
    to_copy: list[tuple[Path, Path, int]] = []   # (src_file, dst_file, size)
    for src_file in _iter_files(src):
        try:
            rel   = str(src_file.relative_to(src))
            size  = src_file.stat().st_size
            if rel not in dst_index or (dst_index[rel] != size):
                dst_file = dst / rel
                to_copy.append((src_file, dst_file, size))
        except Exception:
            pass

    files_total = len(to_copy)
    bytes_total = sum(s for _, _, s in to_copy)

    for src_file, dst_file, size in to_copy:
        if dry_run:
            files_done += 1
            bytes_done += size
        else:
            try:
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src_file), str(dst_file))
                result.copied   += 1
                result.bytes_copied += size
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"{src_file}: {exc}")

        files_done += 1
        bytes_done += size if not dry_run else 0

        if progress_cb:
            elapsed = time.monotonic() - start
            speed   = result.bytes_copied / elapsed if elapsed > 0 else 0
            remain  = bytes_total - bytes_done
            eta     = remain / speed if speed > 0 else 0
            progress_cb({
                "files_done":  files_done,
                "files_total": files_total,
                "bytes_done_human":  _human(result.bytes_copied),
                "bytes_total_human": _human(bytes_total),
                "speed_human": _speed(speed),
                "eta_sec":     int(eta),
                "pct":         round(files_done / files_total * 100, 1) if files_total else 100,
                "current_file": str(src_file),
            })

    # Delete extra files on dest (mirror mode)
    deleted = 0
    if delete_extra and not dry_run:
        src_index: set[str] = set()
        for f in _iter_files(src):
            try:
                src_index.add(str(f.relative_to(src)))
            except Exception:
                pass
        for rel, _ in dst_index.items():
            if rel not in src_index:
                try:
                    (dst / rel).unlink()
                    deleted += 1
                except Exception:
                    pass

    result.elapsed_sec = time.monotonic() - start
    result.skipped = len(dst_index) - result.copied  # files already current

    # Verify
    if verify and not dry_run and result.copied > 0:
        for src_file, dst_file, _ in to_copy:
            if dst_file.exists():
                try:
                    if _file_hash(str(src_file)) == _file_hash(str(dst_file)):
                        result.verified_ok += 1
                    else:
                        result.verified_fail += 1
                        result.errors.append(f"HASH MISMATCH: {dst_file}")
                except Exception:
                    pass

    return result


def transfer_summary(result: TransferResult, plan: TransferPlan) -> dict:
    elapsed = result.elapsed_sec
    speed_bps = result.bytes_copied / elapsed if elapsed > 0 else 0
    return {
        "copied":        result.copied,
        "skipped":       result.skipped,
        "failed":        result.failed,
        "verified_ok":   result.verified_ok,
        "verified_fail": result.verified_fail,
        "bytes_copied":  result.bytes_copied,
        "bytes_human":   _human(result.bytes_copied),
        "elapsed_sec":   round(elapsed, 1),
        "elapsed_human": f"{int(elapsed//3600)}h {int((elapsed%3600)//60)}m {int(elapsed%60)}s",
        "avg_speed":     _speed(speed_bps),
        "errors":        result.errors[:20],
        "total_files":   plan.total_files,
        "total_bytes":   plan.total_bytes,
        "total_human":   _human(plan.total_bytes),
    }
