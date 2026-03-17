"""Tests for the Automated Repair & Self-Healing Framework (engines/self_healer.py).

Covers:
  - Issue detection (missing directories, broken INI paths, empty databases, missing media)
  - Repair execution (create missing dirs, create media structure)
  - Dry-run mode
  - Backup creation and rollback
  - Diagnostic report generation
  - Healing report save/load
  - Check/repair registry
  - Dataclass serialization
"""

import json
import tempfile
from pathlib import Path

import pytest

from engines.self_healer import (
    DiagnosticReport,
    HealingReport,
    Issue,
    RepairResult,
    _CHECK_REGISTRY,
    _REPAIR_REGISTRY,
    _find_repair_fn,
    check_broken_ini_paths,
    check_empty_databases,
    check_missing_directories,
    check_missing_media,
    check_settings_without_exe,
    create_backup,
    get_issue_summary,
    heal,
    list_checks,
    list_repair_prefixes,
    load_healing_history,
    repair_missing_directory,
    repair_missing_media,
    run_diagnostics,
    save_healing_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_hs_root(tmp_path):
    """Create a minimal HyperSpin directory structure."""
    hs = tmp_path / "HyperSpin"
    (hs / "Settings").mkdir(parents=True)
    (hs / "Databases" / "MAME").mkdir(parents=True)
    (hs / "Media" / "MAME" / "Images" / "Wheel").mkdir(parents=True)
    (hs / "Themes").mkdir()
    return hs


@pytest.fixture
def tmp_hs_incomplete(tmp_path):
    """Create an incomplete HyperSpin structure with known issues."""
    hs = tmp_path / "IncompleteHS"
    (hs / "Settings").mkdir(parents=True)
    # Missing: Databases, Media, Themes directories
    return hs


@pytest.fixture
def tmp_hs_with_broken_paths(tmp_path):
    """Create HyperSpin with INI files containing broken paths."""
    hs = tmp_path / "BrokenHS"
    (hs / "Settings").mkdir(parents=True)
    (hs / "Databases").mkdir()
    (hs / "Media").mkdir()
    (hs / "Themes").mkdir()

    # Create INI with broken path
    ini = hs / "Settings" / "TestSystem.ini"
    ini.write_text(
        "[exe]\n"
        "Path=C:\\NonExistent\\Path\\emulator.exe\n"
        "ROM_Path=C:\\NonExistent\\ROMs\n"
        "UseRocketLauncher=true\n"
        "RocketLauncherPath=C:\\NonExistent\\RL.exe\n",
        encoding="utf-8",
    )
    return hs


# ---------------------------------------------------------------------------
# check_missing_directories
# ---------------------------------------------------------------------------

class TestCheckMissingDirectories:
    def test_all_present(self, tmp_hs_root):
        issues = check_missing_directories(tmp_hs_root)
        assert len(issues) == 0

    def test_missing_dirs(self, tmp_hs_incomplete):
        issues = check_missing_directories(tmp_hs_incomplete)
        assert len(issues) >= 2  # At least Databases, Media, Themes missing
        missing_names = [i.id for i in issues]
        assert any("databases" in n for n in missing_names)
        assert all(i.repairable for i in issues)

    def test_issue_fields(self, tmp_hs_incomplete):
        issues = check_missing_directories(tmp_hs_incomplete)
        for issue in issues:
            assert issue.category == "path"
            assert issue.severity in ("error", "warn")
            assert issue.filepath


# ---------------------------------------------------------------------------
# check_broken_ini_paths
# ---------------------------------------------------------------------------

class TestCheckBrokenIniPaths:
    def test_broken_paths_detected(self, tmp_hs_with_broken_paths):
        issues = check_broken_ini_paths(tmp_hs_with_broken_paths)
        assert len(issues) >= 1
        assert all(i.category == "config" for i in issues)

    def test_no_settings_dir(self, tmp_path):
        issues = check_broken_ini_paths(tmp_path / "nope")
        assert issues == []


# ---------------------------------------------------------------------------
# check_empty_databases
# ---------------------------------------------------------------------------

class TestCheckEmptyDatabases:
    def test_missing_xml(self, tmp_hs_root):
        # MAME dir exists but no XML inside
        issues = check_empty_databases(tmp_hs_root)
        assert len(issues) >= 1
        assert any("missing_db_MAME" in i.id for i in issues)

    def test_empty_xml(self, tmp_hs_root):
        xml = tmp_hs_root / "Databases" / "MAME" / "MAME.xml"
        xml.write_text("<menu/>", encoding="utf-8")  # minimal content
        issues = check_empty_databases(tmp_hs_root)
        assert any("empty_db" in i.id for i in issues)

    def test_no_db_dir(self, tmp_path):
        issues = check_empty_databases(tmp_path / "nope")
        assert issues == []


# ---------------------------------------------------------------------------
# check_missing_media
# ---------------------------------------------------------------------------

class TestCheckMissingMedia:
    def test_media_present(self, tmp_hs_root):
        # MAME has both Databases and Media
        issues = check_missing_media(tmp_hs_root)
        assert not any("MAME" in i.id for i in issues)

    def test_media_missing(self, tmp_path):
        hs = tmp_path / "HS"
        (hs / "Databases" / "NES").mkdir(parents=True)
        (hs / "Media").mkdir()
        issues = check_missing_media(hs)
        assert len(issues) >= 1
        assert any("NES" in i.description for i in issues)
        assert issues[0].repairable


# ---------------------------------------------------------------------------
# check_settings_without_exe
# ---------------------------------------------------------------------------

class TestCheckSettingsWithoutExe:
    def test_no_exe_section(self, tmp_path):
        hs = tmp_path / "HS"
        (hs / "Settings").mkdir(parents=True)
        ini = hs / "Settings" / "NoExe.ini"
        ini.write_text("[Wheel]\nSpeed=fast\n", encoding="utf-8")
        issues = check_settings_without_exe(hs)
        assert len(issues) >= 1
        assert any("no_exe_section" in i.id for i in issues)

    def test_with_exe_section(self, tmp_hs_with_broken_paths):
        issues = check_settings_without_exe(tmp_hs_with_broken_paths)
        # TestSystem.ini has [exe] section
        assert not any("TestSystem" in i.id for i in issues)


# ---------------------------------------------------------------------------
# repair_missing_directory
# ---------------------------------------------------------------------------

class TestRepairMissingDirectory:
    def test_create_directory(self, tmp_path):
        target = tmp_path / "new_dir"
        issue = Issue(
            id="missing_dir_test",
            category="path",
            severity="error",
            description="Test missing dir",
            filepath=str(target),
            repairable=True,
        )
        result = repair_missing_directory(issue, tmp_path / "backups")
        assert result.success is True
        assert target.exists()

    def test_already_exists(self, tmp_path):
        target = tmp_path / "existing"
        target.mkdir()
        issue = Issue(
            id="missing_dir_existing",
            category="path",
            severity="error",
            description="Dir already exists",
            filepath=str(target),
            repairable=True,
        )
        result = repair_missing_directory(issue, tmp_path / "backups")
        assert result.success is True


# ---------------------------------------------------------------------------
# repair_missing_media
# ---------------------------------------------------------------------------

class TestRepairMissingMedia:
    def test_create_media_structure(self, tmp_path):
        target = tmp_path / "Media" / "NES"
        issue = Issue(
            id="missing_media_NES",
            category="path",
            severity="info",
            description="No media for NES",
            filepath=str(target),
            repairable=True,
        )
        result = repair_missing_media(issue, tmp_path / "backups")
        assert result.success is True
        assert target.exists()
        assert (target / "Images" / "Wheel").exists()
        assert (target / "Video").exists()
        assert (target / "Themes").exists()


# ---------------------------------------------------------------------------
# create_backup
# ---------------------------------------------------------------------------

class TestCreateBackup:
    def test_backup_file(self, tmp_path):
        original = tmp_path / "test.ini"
        original.write_text("content", encoding="utf-8")
        backup_dir = tmp_path / "backups"

        backup_path = create_backup(original, backup_dir)
        assert backup_path != ""
        assert Path(backup_path).exists()
        assert Path(backup_path).read_text(encoding="utf-8") == "content"

    def test_backup_nonexistent(self, tmp_path):
        result = create_backup(tmp_path / "nope.ini", tmp_path / "backups")
        assert result == ""


# ---------------------------------------------------------------------------
# run_diagnostics
# ---------------------------------------------------------------------------

class TestRunDiagnostics:
    def test_full_scan(self, tmp_hs_incomplete):
        report = run_diagnostics(tmp_hs_incomplete)
        assert isinstance(report, DiagnosticReport)
        assert report.total_issues > 0
        assert report.scan_time

    def test_scan_healthy(self, tmp_hs_root):
        # Add the required DB XML to make it "healthier"
        xml = tmp_hs_root / "Databases" / "MAME" / "MAME.xml"
        xml.write_text('<?xml version="1.0"?><menu>' + 'x' * 100 + '</menu>', encoding="utf-8")
        report = run_diagnostics(tmp_hs_root)
        assert isinstance(report, DiagnosticReport)

    def test_scan_specific_checks(self, tmp_hs_incomplete):
        report = run_diagnostics(tmp_hs_incomplete, checks=["missing_directories"])
        # Should only find issues from missing_directories check
        assert report.total_issues > 0
        assert all(i.category == "path" for i in report.issues)

    def test_report_to_dict(self, tmp_hs_incomplete):
        report = run_diagnostics(tmp_hs_incomplete)
        d = report.to_dict()
        assert "total_issues" in d
        assert "issues" in d
        assert isinstance(d["issues"], list)


# ---------------------------------------------------------------------------
# heal
# ---------------------------------------------------------------------------

class TestHeal:
    def test_dry_run(self, tmp_hs_incomplete):
        report = heal(tmp_hs_incomplete, dry_run=True)
        assert isinstance(report, HealingReport)
        assert report.dry_run is True
        assert report.total_attempted > 0
        assert report.total_success > 0
        # Verify nothing was actually created
        assert not (tmp_hs_incomplete / "Databases").exists()

    def test_actual_repair(self, tmp_hs_incomplete):
        report = heal(tmp_hs_incomplete, dry_run=False)
        assert report.dry_run is False
        assert report.total_success > 0
        # Verify directories were actually created
        assert (tmp_hs_incomplete / "Databases").exists()

    def test_category_filter(self, tmp_hs_incomplete):
        report = heal(tmp_hs_incomplete, dry_run=True, categories=["path"])
        assert report.total_attempted > 0
        # Only path category issues should be attempted

    def test_max_repairs_limit(self, tmp_hs_incomplete):
        report = heal(tmp_hs_incomplete, dry_run=True, max_repairs=1)
        assert report.total_attempted <= 1

    def test_healing_report_to_dict(self, tmp_hs_incomplete):
        report = heal(tmp_hs_incomplete, dry_run=True)
        d = report.to_dict()
        assert "dry_run" in d
        assert "repairs" in d
        assert isinstance(d["repairs"], list)


# ---------------------------------------------------------------------------
# save/load healing report
# ---------------------------------------------------------------------------

class TestHealingPersistence:
    def test_save_and_load(self, tmp_path):
        report = HealingReport(
            timestamp="2024-01-01T00:00:00Z",
            dry_run=False,
            total_attempted=3,
            total_success=2,
            total_failed=1,
            repairs=[
                RepairResult(issue_id="test_1", success=True, action_taken="fixed"),
            ],
        )
        output_dir = tmp_path / "reports"
        saved_path = save_healing_report(report, output_dir)
        assert saved_path != ""
        assert Path(saved_path).exists()

        history = load_healing_history(output_dir)
        assert len(history) == 1
        assert history[0]["total_attempted"] == 3

    def test_load_empty_dir(self, tmp_path):
        history = load_healing_history(tmp_path / "empty")
        assert history == []


# ---------------------------------------------------------------------------
# Registry and utility
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_list_checks(self):
        checks = list_checks()
        assert isinstance(checks, list)
        assert "missing_directories" in checks
        assert "broken_ini_paths" in checks
        assert "empty_databases" in checks

    def test_list_repair_prefixes(self):
        prefixes = list_repair_prefixes()
        assert "missing_dir_" in prefixes
        assert "missing_media_" in prefixes

    def test_find_repair_fn(self):
        fn = _find_repair_fn("missing_dir_settings")
        assert fn is not None
        assert fn == repair_missing_directory

    def test_find_repair_fn_missing(self):
        fn = _find_repair_fn("unknown_issue_xyz")
        assert fn is None

    def test_get_issue_summary(self):
        report = DiagnosticReport(issues=[
            Issue("a", "config", "error", "err1"),
            Issue("b", "config", "warn", "warn1"),
            Issue("c", "path", "error", "err2"),
        ])
        summary = get_issue_summary(report)
        assert summary["config"] == 2
        assert summary["path"] == 1


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_issue_to_dict(self):
        i = Issue("id1", "config", "error", "desc", "/path", True, "fix it")
        d = i.to_dict()
        assert d["id"] == "id1"
        assert d["repairable"] is True

    def test_repair_result_to_dict(self):
        r = RepairResult("id1", True, "fixed", "before", "after", "/backup")
        d = r.to_dict()
        assert d["success"] is True
        assert d["backup_path"] == "/backup"

    def test_diagnostic_report_to_dict(self):
        r = DiagnosticReport(total_issues=5, errors=2, warnings=3)
        d = r.to_dict()
        assert d["total_issues"] == 5

    def test_healing_report_to_dict(self):
        r = HealingReport(dry_run=True, total_attempted=3)
        d = r.to_dict()
        assert d["dry_run"] is True
