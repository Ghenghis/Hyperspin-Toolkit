"""
M66 -- Drive Integrity Checker Engine
Compare a KINHANK drive against a reference drive or known-good manifest
to detect missing content, zero-byte files, corruption, and completeness.
"""

import csv
import hashlib
import json
import os
import re
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set

logger = logging.getLogger("integrity_checker")


@dataclass
class IntegrityIssue:
    """A single integrity issue found on a drive."""
    severity: str       # critical, warning, info
    category: str       # missing_dir, missing_file, zero_byte, size_mismatch, extra_file
    path: str
    message: str
    expected: str = ""  # what was expected
    actual: str = ""    # what was found


@dataclass
class IntegrityReport:
    """Complete integrity report for a drive."""
    drive_letter: str
    variant: str
    reference_drive: str = ""
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    issues: List[IntegrityIssue] = field(default_factory=list)
    structure_score: float = 0.0     # 0-100%
    content_score: float = 0.0       # 0-100%
    overall_score: float = 0.0       # 0-100%
    zero_byte_files: int = 0
    missing_dirs: int = 0
    missing_files: int = 0
    extra_files: int = 0

    def add_issue(self, severity: str, category: str, path: str,
                  message: str, expected: str = "", actual: str = ""):
        self.issues.append(IntegrityIssue(
            severity=severity, category=category, path=path,
            message=message, expected=expected, actual=actual,
        ))
        if severity == "critical":
            self.failed += 1
        elif severity == "warning":
            self.warnings += 1
        self.total_checks += 1

    def add_pass(self):
        self.passed += 1
        self.total_checks += 1

    def calculate_scores(self):
        if self.total_checks > 0:
            self.overall_score = round(100 * self.passed / self.total_checks, 1)

    def summary(self) -> str:
        self.calculate_scores()
        lines = [
            f"Integrity Report: {self.drive_letter} (Variant {self.variant})",
            f"  Reference: {self.reference_drive or 'built-in checks'}",
            f"  Score: {self.overall_score}% ({self.passed}/{self.total_checks} passed)",
            f"  Structure: {self.structure_score}% | Content: {self.content_score}%",
            f"  Issues: {self.failed} critical, {self.warnings} warnings",
            f"  Zero-byte files: {self.zero_byte_files}",
            f"  Missing dirs: {self.missing_dirs}",
            f"  Missing files: {self.missing_files}",
        ]
        # Group critical issues
        critical = [i for i in self.issues if i.severity == "critical"]
        if critical:
            lines.append(f"\n  Critical Issues ({len(critical)}):")
            for issue in critical[:20]:
                lines.append(f"    [{issue.category}] {issue.message}")
        return "\n".join(lines)

    def to_csv(self, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        fieldnames = ["severity", "category", "path", "message", "expected", "actual"]
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for issue in self.issues:
                writer.writerow(asdict(issue))
        return output_path

    def to_json(self, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        data = {
            "drive_letter": self.drive_letter,
            "variant": self.variant,
            "reference_drive": self.reference_drive,
            "overall_score": self.overall_score,
            "structure_score": self.structure_score,
            "content_score": self.content_score,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "zero_byte_files": self.zero_byte_files,
            "missing_dirs": self.missing_dirs,
            "issues": [asdict(i) for i in self.issues],
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return output_path


# ---------------------------------------------------------------------------
# Zero-byte / corruption scanner
# ---------------------------------------------------------------------------

def scan_zero_byte_files(drive_root: str, max_depth: int = 4,
                         exclude_dirs: Optional[Set[str]] = None) -> List[str]:
    """Find zero-byte files on a drive (potential corruption indicators)."""
    zero_files = []
    exclude = exclude_dirs or {"$RECYCLE.BIN", "System Volume Information", ".Trash"}

    for root, dirs, files in os.walk(drive_root):
        # Respect max depth
        depth = root.replace(drive_root, "").count(os.sep)
        if depth >= max_depth:
            dirs.clear()
            continue

        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude]

        for f in files:
            fpath = os.path.join(root, f)
            try:
                if os.path.getsize(fpath) == 0:
                    zero_files.append(fpath)
            except OSError:
                pass

    return zero_files


# ---------------------------------------------------------------------------
# Structure comparison (drive vs reference)
# ---------------------------------------------------------------------------

def compare_directory_structure(
    target_root: str,
    reference_root: str,
    relative_path: str = "",
    max_depth: int = 3,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Compare directory structure between target and reference.

    Returns: (missing_in_target, extra_in_target, common_dirs)
    """
    target_path = os.path.join(target_root, relative_path) if relative_path else target_root
    ref_path = os.path.join(reference_root, relative_path) if relative_path else reference_root

    if not os.path.isdir(ref_path):
        return [], [], []
    if not os.path.isdir(target_path):
        # Entire directory missing
        ref_dirs = set()
        for entry in os.scandir(ref_path):
            if entry.is_dir():
                ref_dirs.add(entry.name)
        return list(ref_dirs), [], []

    ref_dirs = set()
    target_dirs = set()

    try:
        for entry in os.scandir(ref_path):
            if entry.is_dir() and entry.name not in ("$RECYCLE.BIN", "System Volume Information"):
                ref_dirs.add(entry.name)
    except OSError:
        pass

    try:
        for entry in os.scandir(target_path):
            if entry.is_dir() and entry.name not in ("$RECYCLE.BIN", "System Volume Information"):
                target_dirs.add(entry.name)
    except OSError:
        pass

    missing = sorted(ref_dirs - target_dirs)
    extra = sorted(target_dirs - ref_dirs)
    common = sorted(ref_dirs & target_dirs)

    return missing, extra, common


# ---------------------------------------------------------------------------
# Variant-specific integrity checks
# ---------------------------------------------------------------------------

def check_variant_a(drive_root: str, reference_root: Optional[str] = None) -> IntegrityReport:
    """Check integrity of Variant A (HyperSpin) drive."""
    report = IntegrityReport(drive_letter=drive_root[:2], variant="A")
    if reference_root:
        report.reference_drive = reference_root[:2]

    arcade = os.path.join(drive_root, "Arcade")

    # Check required structure
    required_dirs = [
        "Arcade", "Arcade\\HyperSpin.exe", "Arcade\\Databases",
        "Arcade\\Media", "Arcade\\RocketLauncher", "Arcade\\Settings",
    ]
    structure_checks = 0
    structure_pass = 0
    for rd in required_dirs:
        path = os.path.join(drive_root, rd)
        structure_checks += 1
        if os.path.exists(path):
            structure_pass += 1
            report.add_pass()
        else:
            report.add_issue("critical", "missing_dir", rd,
                             f"Required path missing: {rd}")
            report.missing_dirs += 1

    report.structure_score = round(100 * structure_pass / max(1, structure_checks), 1)

    # Compare against reference if provided
    if reference_root and os.path.isdir(reference_root):
        _compare_databases(report, drive_root, reference_root)
    else:
        # Self-check: verify databases exist for systems
        db_path = os.path.join(arcade, "Databases")
        if os.path.isdir(db_path):
            db_systems = [e.name for e in os.scandir(db_path) if e.is_dir()]
            for sys_name in db_systems:
                xml_file = os.path.join(db_path, sys_name, f"{sys_name}.xml")
                if os.path.isfile(xml_file):
                    if os.path.getsize(xml_file) == 0:
                        report.add_issue("warning", "zero_byte", xml_file,
                                         f"Zero-byte database: {sys_name}.xml")
                        report.zero_byte_files += 1
                    else:
                        report.add_pass()
                else:
                    report.add_issue("warning", "missing_file", xml_file,
                                     f"No XML database for system: {sys_name}")

    # Zero-byte scan
    zeros = scan_zero_byte_files(arcade, max_depth=3)
    report.zero_byte_files += len(zeros)
    for zf in zeros[:50]:
        report.add_issue("warning", "zero_byte", zf,
                         f"Zero-byte file: {os.path.relpath(zf, drive_root)}")

    report.calculate_scores()
    return report


def check_variant_b_core(drive_root: str, reference_root: Optional[str] = None) -> IntegrityReport:
    """Check integrity of Variant B-C (CORE - TYPE R) drive."""
    report = IntegrityReport(drive_letter=drive_root[:2], variant="B-C")
    if reference_root:
        report.reference_drive = reference_root[:2]

    core_path = os.path.join(drive_root, "CORE - TYPE R")

    # Required structure
    required = [
        "CORE - TYPE R",
        "CORE - TYPE R\\CORE.exe",
        "CORE - TYPE R\\settings.conf",
        "CORE - TYPE R\\collections",
        "CORE - TYPE R\\collections\\COMPUTERS",
        "CORE - TYPE R\\collections\\COMPUTERS\\roms",
    ]
    structure_checks = 0
    structure_pass = 0
    for rd in required:
        path = os.path.join(drive_root, rd)
        structure_checks += 1
        if os.path.exists(path):
            structure_pass += 1
            report.add_pass()
        else:
            report.add_issue("critical", "missing_dir", rd,
                             f"Required path missing: {rd}")
            report.missing_dirs += 1

    report.structure_score = round(100 * structure_pass / max(1, structure_checks), 1)

    # Check embedded frontends
    base = os.path.join(core_path, "collections", "COMPUTERS", "roms")
    expected_frontends = {
        "HyperSpin Attraction": {"subdir": "collections", "min_count": 50},
        "Hyperspin TeknoParrot": {"subdir": "collections", "min_count": 1},
        "LaunchBox": {"subdir": "Games", "min_count": 10},
        "Playnite": {"subdir": "PC Games", "min_count": 10},
        "RetroBat": {"subdir": "roms", "min_count": 50},
        "Kodi": {"subdir": None, "min_count": 0},
    }

    content_checks = 0
    content_pass = 0
    for fe_name, spec in expected_frontends.items():
        fe_path = os.path.join(base, fe_name)
        content_checks += 1
        if not os.path.isdir(fe_path):
            report.add_issue("critical", "missing_dir", fe_path,
                             f"Missing frontend: {fe_name}")
            report.missing_dirs += 1
            continue

        if spec["subdir"]:
            sub_path = os.path.join(fe_path, spec["subdir"])
            if not os.path.isdir(sub_path):
                report.add_issue("warning", "missing_dir", sub_path,
                                 f"{fe_name}: missing content dir {spec['subdir']}/")
                continue

            try:
                count = sum(1 for e in os.scandir(sub_path) if e.is_dir())
            except OSError:
                count = 0

            if count >= spec["min_count"]:
                content_pass += 1
                report.add_pass()
            else:
                report.add_issue("warning", "size_mismatch", sub_path,
                                 f"{fe_name}: only {count} items (expected >={spec['min_count']})",
                                 expected=str(spec["min_count"]),
                                 actual=str(count))
        else:
            content_pass += 1
            report.add_pass()

    report.content_score = round(100 * content_pass / max(1, content_checks), 1)

    # Zero-byte scan on CORE
    zeros = scan_zero_byte_files(core_path, max_depth=3)
    report.zero_byte_files += len(zeros)
    for zf in zeros[:50]:
        report.add_issue("info", "zero_byte", zf,
                         f"Zero-byte: {os.path.relpath(zf, drive_root)}")

    # Check for user files on root (non-KINHANK)
    kinhank_dirs = {"CORE - TYPE R", "Installation", "Arcade",
                    "$RECYCLE.BIN", "System Volume Information"}
    try:
        for entry in os.scandir(drive_root):
            if entry.name not in kinhank_dirs:
                report.add_issue("info", "extra_file", entry.path,
                                 f"Non-KINHANK item on root: {entry.name}")
                report.extra_files += 1
    except OSError:
        pass

    report.calculate_scores()
    return report


def check_variant_b_attraction(drive_root: str, reference_root: Optional[str] = None) -> IntegrityReport:
    """Check integrity of Variant B-A (AttractMode) drive."""
    report = IntegrityReport(drive_letter=drive_root[:2], variant="B-A")
    if reference_root:
        report.reference_drive = reference_root[:2]

    arcade = os.path.join(drive_root, "Arcade")

    # Required structure
    required = [
        "Arcade", "Arcade\\collections", "Arcade\\romlists",
        "Arcade\\emulators",
    ]
    structure_checks = 0
    structure_pass = 0
    for rd in required:
        path = os.path.join(drive_root, rd)
        structure_checks += 1
        if os.path.exists(path):
            structure_pass += 1
            report.add_pass()
        else:
            report.add_issue("critical", "missing_dir", rd,
                             f"Required path missing: {rd}")
            report.missing_dirs += 1

    report.structure_score = round(100 * structure_pass / max(1, structure_checks), 1)

    # Check collections vs romlists alignment
    coll_path = os.path.join(arcade, "collections")
    rl_path = os.path.join(arcade, "romlists")
    if os.path.isdir(coll_path) and os.path.isdir(rl_path):
        collections = set(e.name for e in os.scandir(coll_path)
                          if e.is_dir() and e.name != "Settings")
        romlists = set(Path(e.name).stem for e in os.scandir(rl_path)
                       if e.is_file() and e.name.endswith(".txt"))

        # Collections without romlists
        for c in sorted(collections - romlists):
            report.add_issue("warning", "missing_file",
                             os.path.join(rl_path, f"{c}.txt"),
                             f"Collection '{c}' has no romlist")

        content_checks = len(collections)
        content_pass = len(collections & romlists)
        report.content_score = round(100 * content_pass / max(1, content_checks), 1)

    # Compare with reference if available
    if reference_root:
        ref_coll = os.path.join(reference_root, "Arcade", "collections")
        if os.path.isdir(ref_coll):
            missing, extra, common = compare_directory_structure(
                drive_root, reference_root, "Arcade\\collections"
            )
            for m in missing:
                report.add_issue("critical", "missing_dir",
                                 os.path.join(coll_path, m),
                                 f"Missing collection vs reference: {m}")
                report.missing_dirs += 1

    # Zero-byte scan
    zeros = scan_zero_byte_files(arcade, max_depth=3)
    report.zero_byte_files += len(zeros)
    for zf in zeros[:50]:
        report.add_issue("warning", "zero_byte", zf,
                         f"Zero-byte: {os.path.relpath(zf, drive_root)}")

    report.calculate_scores()
    return report


def check_variant_c_data(drive_root: str) -> IntegrityReport:
    """Check integrity of Variant C-D (Batocera data) drive."""
    report = IntegrityReport(drive_letter=drive_root[:2], variant="C-D")

    required = ["roms", "bios"]
    structure_checks = 0
    structure_pass = 0
    for rd in required:
        path = os.path.join(drive_root, rd)
        structure_checks += 1
        if os.path.isdir(path):
            structure_pass += 1
            report.add_pass()
        else:
            report.add_issue("critical", "missing_dir", rd,
                             f"Required dir missing: {rd}")
            report.missing_dirs += 1

    report.structure_score = round(100 * structure_pass / max(1, structure_checks), 1)

    # Check each ROM system dir has content
    roms_path = os.path.join(drive_root, "roms")
    if os.path.isdir(roms_path):
        empty_systems = 0
        total_systems = 0
        for sys_entry in os.scandir(roms_path):
            if sys_entry.is_dir():
                total_systems += 1
                try:
                    has_files = any(e.is_file() for e in os.scandir(sys_entry.path))
                except OSError:
                    has_files = False
                if has_files:
                    report.add_pass()
                else:
                    empty_systems += 1
                    report.add_issue("info", "missing_file", sys_entry.path,
                                     f"Empty ROM system dir: {sys_entry.name}")
        if total_systems > 0:
            report.content_score = round(
                100 * (total_systems - empty_systems) / total_systems, 1
            )

    report.calculate_scores()
    return report


def _compare_databases(report: IntegrityReport, target_root: str, reference_root: str):
    """Compare HyperSpin databases between target and reference."""
    target_db = os.path.join(target_root, "Arcade", "Databases")
    ref_db = os.path.join(reference_root, "Arcade", "Databases")

    if not os.path.isdir(ref_db) or not os.path.isdir(target_db):
        return

    ref_systems = set(e.name for e in os.scandir(ref_db) if e.is_dir())
    target_systems = set(e.name for e in os.scandir(target_db) if e.is_dir())

    for sys_name in sorted(ref_systems - target_systems):
        report.add_issue("critical", "missing_dir",
                         os.path.join(target_db, sys_name),
                         f"Missing database system: {sys_name}")
        report.missing_dirs += 1

    content_pass = len(ref_systems & target_systems)
    content_total = len(ref_systems)
    report.content_score = round(100 * content_pass / max(1, content_total), 1)


# ---------------------------------------------------------------------------
# Auto-detect and check
# ---------------------------------------------------------------------------

def check_integrity(drive_letter: str, reference_drive: Optional[str] = None,
                    variant: Optional[str] = None) -> IntegrityReport:
    """
    Run integrity checks on a KINHANK drive.

    Args:
        drive_letter: Drive to check (e.g. "L")
        reference_drive: Optional reference drive for comparison (e.g. "K")
        variant: Force variant or auto-detect
    """
    drive = drive_letter.strip().rstrip(":\\")
    drive_root = f"{drive}:\\"
    ref_root = None
    if reference_drive:
        ref = reference_drive.strip().rstrip(":\\")
        ref_root = f"{ref}:\\"

    if not os.path.exists(drive_root):
        report = IntegrityReport(drive_letter=f"{drive}:", variant=variant or "?")
        report.add_issue("critical", "missing_dir", drive_root,
                         f"Drive {drive}: not accessible")
        return report

    if not variant:
        from engines.drive_fingerprint import fingerprint_drive
        fp = fingerprint_drive(drive)
        variant = fp.variant

    if variant == "A":
        return check_variant_a(drive_root, ref_root)
    elif variant == "B-A":
        return check_variant_b_attraction(drive_root, ref_root)
    elif variant == "B-C":
        return check_variant_b_core(drive_root, ref_root)
    elif variant == "C-D":
        return check_variant_c_data(drive_root)
    else:
        report = IntegrityReport(drive_letter=f"{drive}:", variant=variant or "?")
        report.add_issue("warning", "missing_dir", drive_root,
                         f"No integrity checks defined for variant: {variant}")
        return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python integrity_checker.py <drive> [reference_drive] [variant]")
        print("  Examples:")
        print("    python integrity_checker.py L")
        print("    python integrity_checker.py L K")
        print("    python integrity_checker.py D I A")
        sys.exit(1)

    drive = sys.argv[1]
    ref = sys.argv[2] if len(sys.argv) > 2 else None
    forced_variant = sys.argv[3] if len(sys.argv) > 3 else None

    report = check_integrity(drive, ref, forced_variant)
    print(report.summary())

    # Save report
    output_base = f"integrity_{drive.strip(':')}_{report.variant}"
    report.to_csv(f"{output_base}.csv")
    report.to_json(f"{output_base}.json")
    print(f"\nSaved: {output_base}.csv, {output_base}.json")
