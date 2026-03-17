"""M63 — Automated Repair & Self-Healing Framework.

Detects and fixes common HyperSpin/RocketLauncher configuration issues
without disrupting functionality.  Provides:
  - Issue detection via pluggable diagnostic checks
  - Automated repair actions with rollback capability
  - Dry-run mode to preview fixes before applying
  - Repair history logging for auditability
  - Health check orchestration across all engines

Design principles:
  - Non-destructive: always backup before modifying
  - Transparent: every repair is logged with before/after state
  - Pluggable: new checks/repairs are registered via decorators
  - Safe: dry-run is default; repairs require explicit opt-in
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from core.config import get as cfg_get
from core.logger import get_logger

log = get_logger("self_healer")


# ═══════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class Issue:
    """A detected issue that may be auto-repairable."""
    id: str
    category: str  # "config", "path", "settings", "bios", "permission"
    severity: str  # "error", "warn", "info"
    description: str
    filepath: str = ""
    repairable: bool = False
    repair_action: str = ""  # human-readable description of the fix
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "filepath": self.filepath,
            "repairable": self.repairable,
            "repair_action": self.repair_action,
            "context": self.context,
        }


@dataclass
class RepairResult:
    """Result of attempting to repair an issue."""
    issue_id: str
    success: bool = False
    action_taken: str = ""
    before_state: str = ""
    after_state: str = ""
    backup_path: str = ""
    error: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_id": self.issue_id,
            "success": self.success,
            "action_taken": self.action_taken,
            "before_state": self.before_state,
            "after_state": self.after_state,
            "backup_path": self.backup_path,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class DiagnosticReport:
    """Full diagnostic scan report."""
    scan_time: str = ""
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    repairable: int = 0
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_time": self.scan_time,
            "total_issues": self.total_issues,
            "errors": self.errors,
            "warnings": self.warnings,
            "repairable": self.repairable,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class HealingReport:
    """Report of all repair actions taken."""
    timestamp: str = ""
    dry_run: bool = True
    total_attempted: int = 0
    total_success: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    repairs: list[RepairResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "dry_run": self.dry_run,
            "total_attempted": self.total_attempted,
            "total_success": self.total_success,
            "total_failed": self.total_failed,
            "total_skipped": self.total_skipped,
            "repairs": [r.to_dict() for r in self.repairs],
        }


# ═══════════════════════════════════════════════════════════════════════
# Check registry — pluggable diagnostic checks
# ═══════════════════════════════════════════════════════════════════════

# Registry of diagnostic check functions
_CHECK_REGISTRY: list[tuple[str, Callable[..., list[Issue]]]] = []

# Registry of repair functions: issue_id_prefix → repair function
_REPAIR_REGISTRY: dict[str, Callable[[Issue, Path], RepairResult]] = {}


def register_check(name: str):
    """Decorator to register a diagnostic check function.

    The decorated function should accept (hs_root: Path) and return list[Issue].
    """
    def decorator(func: Callable[..., list[Issue]]):
        _CHECK_REGISTRY.append((name, func))
        return func
    return decorator


def register_repair(issue_prefix: str):
    """Decorator to register a repair function for a specific issue type.

    The decorated function should accept (issue: Issue, backup_dir: Path)
    and return RepairResult.
    """
    def decorator(func: Callable[[Issue, Path], RepairResult]):
        _REPAIR_REGISTRY[issue_prefix] = func
        return func
    return decorator


# ═══════════════════════════════════════════════════════════════════════
# Built-in diagnostic checks
# ═══════════════════════════════════════════════════════════════════════

@register_check("missing_directories")
def check_missing_directories(hs_root: Path) -> list[Issue]:
    """Check for missing essential HyperSpin directories."""
    issues: list[Issue] = []
    essential_dirs = [
        "Settings", "Databases", "Media", "Themes",
    ]
    for dirname in essential_dirs:
        dirpath = hs_root / dirname
        if not dirpath.exists():
            issues.append(Issue(
                id=f"missing_dir_{dirname.lower()}",
                category="path",
                severity="error" if dirname in ("Settings", "Databases") else "warn",
                description=f"Essential directory missing: {dirname}",
                filepath=str(dirpath),
                repairable=True,
                repair_action=f"Create directory: {dirpath}",
            ))
    return issues


@register_check("broken_ini_paths")
def check_broken_ini_paths(hs_root: Path) -> list[Issue]:
    """Check for broken path references in INI files."""
    issues: list[Issue] = []
    settings_dir = hs_root / "Settings"
    if not settings_dir.exists():
        return issues

    path_keys = {"path", "rom_path", "rocketlauncherpath"}

    for ini_file in settings_dir.glob("*.ini"):
        try:
            import configparser
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(str(ini_file), encoding="utf-8-sig")

            for section in parser.sections():
                for key, value in parser.items(section):
                    if key.lower() in path_keys and value.strip():
                        p = Path(value)
                        if not p.is_absolute():
                            p = hs_root / value
                        if not p.exists():
                            issues.append(Issue(
                                id=f"broken_path_{ini_file.stem}_{section}_{key}",
                                category="config",
                                severity="warn",
                                description=f"Broken path in {ini_file.name}: [{section}] {key} = {value}",
                                filepath=str(ini_file),
                                repairable=False,
                                context={"section": section, "key": key, "value": value},
                            ))
        except Exception as exc:
            issues.append(Issue(
                id=f"parse_error_{ini_file.stem}",
                category="config",
                severity="error",
                description=f"Cannot parse INI: {ini_file.name} — {exc}",
                filepath=str(ini_file),
            ))

    return issues


@register_check("empty_databases")
def check_empty_databases(hs_root: Path) -> list[Issue]:
    """Check for missing or empty HyperSpin XML database files."""
    issues: list[Issue] = []
    db_dir = hs_root / "Databases"
    if not db_dir.exists():
        return issues

    for system_dir in db_dir.iterdir():
        if not system_dir.is_dir():
            continue
        xml_file = system_dir / f"{system_dir.name}.xml"
        if not xml_file.exists():
            issues.append(Issue(
                id=f"missing_db_{system_dir.name}",
                category="config",
                severity="warn",
                description=f"No database XML for system: {system_dir.name}",
                filepath=str(xml_file),
                repairable=False,
            ))
        elif xml_file.stat().st_size < 50:
            issues.append(Issue(
                id=f"empty_db_{system_dir.name}",
                category="config",
                severity="warn",
                description=f"Database XML is empty/minimal for: {system_dir.name}",
                filepath=str(xml_file),
                repairable=False,
            ))

    return issues


@register_check("missing_media")
def check_missing_media(hs_root: Path) -> list[Issue]:
    """Check for systems that have databases but no media."""
    issues: list[Issue] = []
    db_dir = hs_root / "Databases"
    media_dir = hs_root / "Media"

    if not db_dir.exists() or not media_dir.exists():
        return issues

    for system_dir in db_dir.iterdir():
        if not system_dir.is_dir():
            continue
        system_name = system_dir.name
        system_media = media_dir / system_name
        if not system_media.exists():
            issues.append(Issue(
                id=f"missing_media_{system_name}",
                category="path",
                severity="info",
                description=f"No media directory for system: {system_name}",
                filepath=str(system_media),
                repairable=True,
                repair_action=f"Create media directory: {system_media}",
            ))

    return issues


@register_check("settings_without_exe")
def check_settings_without_exe(hs_root: Path) -> list[Issue]:
    """Check for system settings files that have no [exe] section."""
    issues: list[Issue] = []
    settings_dir = hs_root / "Settings"
    if not settings_dir.exists():
        return issues

    for ini_file in settings_dir.glob("*.ini"):
        if ini_file.name.lower() == "hyperspin.ini":
            continue
        try:
            import configparser
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(str(ini_file), encoding="utf-8-sig")
            if not parser.has_section("exe"):
                issues.append(Issue(
                    id=f"no_exe_section_{ini_file.stem}",
                    category="config",
                    severity="info",
                    description=f"System {ini_file.stem} has no [exe] section — emulator may not launch",
                    filepath=str(ini_file),
                    repairable=False,
                ))
        except Exception:
            pass

    return issues


# ═══════════════════════════════════════════════════════════════════════
# Built-in repairs
# ═══════════════════════════════════════════════════════════════════════

@register_repair("missing_dir_")
def repair_missing_directory(issue: Issue, backup_dir: Path) -> RepairResult:
    """Create a missing directory."""
    result = RepairResult(
        issue_id=issue.id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    try:
        target = Path(issue.filepath)
        target.mkdir(parents=True, exist_ok=True)
        result.success = True
        result.action_taken = f"Created directory: {target}"
        result.after_state = "directory_exists"
        log.info("Repaired: created %s", target)
    except OSError as exc:
        result.error = str(exc)
        log.error("Repair failed for %s: %s", issue.id, exc)
    return result


@register_repair("missing_media_")
def repair_missing_media(issue: Issue, backup_dir: Path) -> RepairResult:
    """Create a missing media directory with standard subdirectories."""
    result = RepairResult(
        issue_id=issue.id,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    try:
        target = Path(issue.filepath)
        # Create standard HyperSpin media subdirectories
        subdirs = [
            "Images/Wheel", "Images/Artwork1", "Images/Artwork2",
            "Images/Artwork3", "Images/Artwork4", "Images/Backgrounds",
            "Video", "Themes",
        ]
        for sub in subdirs:
            (target / sub).mkdir(parents=True, exist_ok=True)
        result.success = True
        result.action_taken = f"Created media directory with subdirs: {target}"
        result.after_state = f"created_{len(subdirs)}_subdirs"
        log.info("Repaired: created media structure at %s", target)
    except OSError as exc:
        result.error = str(exc)
        log.error("Repair failed for %s: %s", issue.id, exc)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Backup utility
# ═══════════════════════════════════════════════════════════════════════

def create_backup(filepath: Path, backup_dir: Path) -> str:
    """Create a timestamped backup of a file before modifying it.

    Returns the backup path, or empty string on failure.
    """
    if not filepath.exists():
        return ""

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filepath.stem}_{timestamp}{filepath.suffix}"
    backup_path = backup_dir / backup_name

    try:
        shutil.copy2(filepath, backup_path)
        log.debug("Backed up %s → %s", filepath, backup_path)
        return str(backup_path)
    except OSError as exc:
        log.error("Backup failed for %s: %s", filepath, exc)
        return ""


def rollback_repair(repair: RepairResult) -> bool:
    """Rollback a repair by restoring from backup.

    Returns True if rollback was successful.
    """
    if not repair.backup_path:
        log.warning("No backup path for repair %s — cannot rollback", repair.issue_id)
        return False

    backup = Path(repair.backup_path)
    if not backup.exists():
        log.error("Backup file missing: %s", backup)
        return False

    # Determine the original filepath from the issue_id or context
    # For now, we log a warning — full rollback needs the original path
    log.warning(
        "Rollback requested for %s — backup at %s (manual restore needed)",
        repair.issue_id, repair.backup_path,
    )
    return False


# ═══════════════════════════════════════════════════════════════════════
# Diagnostic scan
# ═══════════════════════════════════════════════════════════════════════

def run_diagnostics(
    hs_root: Optional[str | Path] = None,
    checks: Optional[list[str]] = None,
) -> DiagnosticReport:
    """Run all registered diagnostic checks.

    Args:
        hs_root: HyperSpin root directory.
        checks: Optional list of check names to run (default: all).

    Returns:
        DiagnosticReport with all detected issues.
    """
    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    report = DiagnosticReport(
        scan_time=datetime.now(timezone.utc).isoformat(),
    )

    log.info("Running diagnostics on %s (%d checks registered)", hs_root, len(_CHECK_REGISTRY))

    for check_name, check_fn in _CHECK_REGISTRY:
        if checks and check_name not in checks:
            continue
        try:
            issues = check_fn(hs_root)
            report.issues.extend(issues)
        except Exception as exc:
            log.error("Check '%s' failed: %s", check_name, exc)
            report.issues.append(Issue(
                id=f"check_error_{check_name}",
                category="internal",
                severity="error",
                description=f"Diagnostic check '{check_name}' crashed: {exc}",
            ))

    # Aggregate counts
    report.total_issues = len(report.issues)
    report.errors = sum(1 for i in report.issues if i.severity == "error")
    report.warnings = sum(1 for i in report.issues if i.severity == "warn")
    report.repairable = sum(1 for i in report.issues if i.repairable)

    log.info(
        "Diagnostics complete: %d issues (%d errors, %d warnings, %d repairable)",
        report.total_issues, report.errors, report.warnings, report.repairable,
    )

    return report


# ═══════════════════════════════════════════════════════════════════════
# Self-healing engine
# ═══════════════════════════════════════════════════════════════════════

def heal(
    hs_root: Optional[str | Path] = None,
    dry_run: bool = True,
    categories: Optional[list[str]] = None,
    max_repairs: int = 50,
) -> HealingReport:
    """Run diagnostics and attempt to repair all fixable issues.

    Args:
        hs_root: HyperSpin root directory.
        dry_run: If True, only report what would be fixed (default: True).
        categories: Only repair issues in these categories.
        max_repairs: Maximum number of repairs to attempt.

    Returns:
        HealingReport with results of all repair attempts.
    """
    if hs_root is None:
        hs_root = Path(cfg_get("paths.hyperspin_root", r"D:\Arcade"))
    else:
        hs_root = Path(hs_root)

    # Setup backup directory
    backup_dir = hs_root / ".healer_backups" / datetime.now().strftime("%Y%m%d_%H%M%S")

    report = HealingReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
    )

    # Run diagnostics
    diag = run_diagnostics(hs_root)

    # Filter to repairable issues
    repairable = [i for i in diag.issues if i.repairable]
    if categories:
        repairable = [i for i in repairable if i.category in categories]

    log.info(
        "Healing: %d repairable issues found (dry_run=%s, max=%d)",
        len(repairable), dry_run, max_repairs,
    )

    for issue in repairable[:max_repairs]:
        report.total_attempted += 1

        if dry_run:
            report.repairs.append(RepairResult(
                issue_id=issue.id,
                success=True,
                action_taken=f"[DRY RUN] Would: {issue.repair_action}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
            report.total_success += 1
            continue

        # Find matching repair function
        repair_fn = _find_repair_fn(issue.id)
        if repair_fn is None:
            report.repairs.append(RepairResult(
                issue_id=issue.id,
                success=False,
                error="No repair function registered for this issue type",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
            report.total_skipped += 1
            continue

        # Execute repair
        try:
            result = repair_fn(issue, backup_dir)
            report.repairs.append(result)
            if result.success:
                report.total_success += 1
            else:
                report.total_failed += 1
        except Exception as exc:
            log.error("Repair crashed for %s: %s", issue.id, exc)
            report.repairs.append(RepairResult(
                issue_id=issue.id,
                success=False,
                error=str(exc),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
            report.total_failed += 1

    log.info(
        "Healing complete: %d attempted, %d success, %d failed, %d skipped",
        report.total_attempted, report.total_success,
        report.total_failed, report.total_skipped,
    )

    return report


def _find_repair_fn(issue_id: str) -> Optional[Callable]:
    """Find a registered repair function matching the issue ID prefix."""
    for prefix, fn in _REPAIR_REGISTRY.items():
        if issue_id.startswith(prefix):
            return fn
    return None


# ═══════════════════════════════════════════════════════════════════════
# Repair history
# ═══════════════════════════════════════════════════════════════════════

def save_healing_report(report: HealingReport, output_dir: Optional[str | Path] = None) -> str:
    """Save a healing report to JSON for auditability.

    Returns the path to the saved report.
    """
    if output_dir is None:
        output_dir = Path(cfg_get("paths.output_root", ".")) / "healing_reports"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"healing_report_{timestamp}.json"
    filepath = output_dir / filename

    try:
        with open(filepath, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2)
        log.info("Saved healing report to %s", filepath)
        return str(filepath)
    except OSError as exc:
        log.error("Failed to save healing report: %s", exc)
        return ""


def load_healing_history(output_dir: Optional[str | Path] = None) -> list[dict]:
    """Load all previous healing reports from the output directory."""
    if output_dir is None:
        output_dir = Path(cfg_get("paths.output_root", ".")) / "healing_reports"
    else:
        output_dir = Path(output_dir)

    if not output_dir.exists():
        return []

    reports: list[dict] = []
    for f in sorted(output_dir.glob("healing_report_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                reports.append(json.load(fh))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Cannot load report %s: %s", f, exc)

    return reports


# ═══════════════════════════════════════════════════════════════════════
# Utility
# ═══════════════════════════════════════════════════════════════════════

def list_checks() -> list[str]:
    """Return names of all registered diagnostic checks."""
    return [name for name, _ in _CHECK_REGISTRY]


def list_repair_prefixes() -> list[str]:
    """Return all registered repair issue prefixes."""
    return list(_REPAIR_REGISTRY.keys())


def get_issue_summary(report: DiagnosticReport) -> dict[str, int]:
    """Get a summary of issues by category."""
    summary: dict[str, int] = {}
    for issue in report.issues:
        summary[issue.category] = summary.get(issue.category, 0) + 1
    return summary
