"""Tests for M9 — RocketLauncher Config Validator engine."""
from __future__ import annotations

import configparser
import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.rl_config_validator import (
    ModuleInfo,
    RLIssue,
    RLValidationReport,
    SystemMapping,
    SEVERITY_ERROR,
    SEVERITY_WARN,
    SEVERITY_INFO,
    _check_path_value,
    _safe_read_ini,
    _validate_paths_in_ini,
    _compute_health_score,
    validate_modules,
    validate_system_settings,
    validate_global_settings,
    validate_plugins,
    validate_rl,
    validate_single_system,
    find_orphaned_settings,
    rl_summary,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def rl_tree(tmp_path):
    """Create a minimal RocketLauncher directory tree for testing."""
    rl = tmp_path / "RocketLauncher"
    rl.mkdir()

    # Executable
    (rl / "RocketLauncher.exe").write_bytes(b"\x00" * 1024)

    # Settings directory with global ini
    settings = rl / "Settings"
    settings.mkdir()
    global_ini = settings / "RocketLauncher.ini"
    global_ini.write_text(
        "[RocketLauncher]\n"
        "StartDir=" + str(rl) + "\n"
        "RomPath=" + str(tmp_path / "ROMs") + "\n",
        encoding="utf-8",
    )

    # Per-system settings
    for sys_name in ("MAME", "Nintendo 64", "Sega Genesis"):
        sys_dir = settings / sys_name
        sys_dir.mkdir()
        ini = sys_dir / f"{sys_name}.ini"
        ini.write_text(
            f"[Settings]\n"
            f"Default_Emulator={sys_name}\n"
            f"Module=RetroArch\n"
            f"RomPath={tmp_path / 'ROMs' / sys_name}\n",
            encoding="utf-8",
        )

    # Modules directory
    modules = rl / "Modules"
    modules.mkdir()
    for mod_name in ("RetroArch", "MAME", "Dolphin"):
        mod_dir = modules / mod_name
        mod_dir.mkdir()
        (mod_dir / f"{mod_name}.ahk").write_text("; launcher script", encoding="utf-8")

    # Plugins directory
    plugins = rl / "Plugins"
    plugins.mkdir()
    plug = plugins / "Fade"
    plug.mkdir()
    (plug / "Fade.ahk").write_text("; fade plugin", encoding="utf-8")
    (plug / "Fade.ini").write_text("[Settings]\nEnabled=true\n", encoding="utf-8")

    # Create ROMs directory so some paths are valid
    roms = tmp_path / "ROMs"
    roms.mkdir()
    (roms / "MAME").mkdir()

    return rl


@pytest.fixture
def broken_rl_tree(tmp_path):
    """Create a RocketLauncher tree with known issues."""
    rl = tmp_path / "RocketLauncher"
    rl.mkdir()
    # No exe
    settings = rl / "Settings"
    settings.mkdir()

    # Global INI with broken path
    global_ini = settings / "RocketLauncher.ini"
    global_ini.write_text(
        "[RocketLauncher]\n"
        "StartDir=Z:\\NonExistent\\Path\n",
        encoding="utf-8",
    )

    # System with reference to non-existent module
    sys_dir = settings / "BadSystem"
    sys_dir.mkdir()
    (sys_dir / "BadSystem.ini").write_text(
        "[Settings]\n"
        "Default_Module=NonExistentModule\n"
        "RomPath=Q:\\fake\\roms\n",
        encoding="utf-8",
    )

    # Modules dir with one empty module (no .ahk)
    modules = rl / "Modules"
    modules.mkdir()
    empty_mod = modules / "EmptyModule"
    empty_mod.mkdir()

    return rl


# ── Unit tests: helpers ─────────────────────────────────────────────

class TestCheckPathValue:
    def test_windows_absolute_path(self):
        is_path, clean = _check_path_value("D:\\Arcade\\Emulators")
        assert is_path is True
        assert clean == "D:\\Arcade\\Emulators"

    def test_quoted_path(self):
        is_path, clean = _check_path_value('"C:\\Program Files\\Test"')
        assert is_path is True
        assert clean == "C:\\Program Files\\Test"

    def test_empty_value(self):
        is_path, _ = _check_path_value("")
        assert is_path is False

    def test_short_value(self):
        is_path, _ = _check_path_value("abc")
        assert is_path is False

    def test_url_not_path(self):
        is_path, _ = _check_path_value("http://localhost:1234")
        assert is_path is False

    def test_https_not_path(self):
        is_path, _ = _check_path_value("https://example.com/foo")
        assert is_path is False

    def test_relative_not_path(self):
        is_path, _ = _check_path_value("relative/path/here")
        assert is_path is False

    def test_semicolon_separated(self):
        is_path, clean = _check_path_value("D:\\path1;D:\\path2")
        assert is_path is True
        assert clean == "D:\\path1"

    def test_pipe_separated(self):
        is_path, clean = _check_path_value("D:\\path1|D:\\path2")
        assert is_path is True
        assert clean == "D:\\path1"


class TestSafeReadIni:
    def test_valid_ini(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text("[Section]\nkey=value\n", encoding="utf-8")
        result = _safe_read_ini(ini)
        assert result is not None
        assert "Section" in result.sections()
        assert result.get("Section", "key") == "value"

    def test_utf8_bom(self, tmp_path):
        ini = tmp_path / "bom.ini"
        ini.write_bytes(b"\xef\xbb\xbf[Section]\nkey=value\n")
        result = _safe_read_ini(ini)
        assert result is not None

    def test_nonexistent_returns_empty(self, tmp_path):
        ini = tmp_path / "nope.ini"
        # _safe_read_ini reads a file; if it doesn't exist configparser returns empty
        result = _safe_read_ini(ini)
        assert result is not None
        assert result.sections() == []

    def test_latin1_fallback(self, tmp_path):
        ini = tmp_path / "latin.ini"
        ini.write_bytes(b"[Sect]\nkey=\xe9\n")
        result = _safe_read_ini(ini)
        assert result is not None


class TestValidatePathsInIni:
    def test_broken_path_detected(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(
            "[Paths]\n"
            "EmuPath=Z:\\NonExistent\\Emulators\n"
            "SomeBool=true\n",
            encoding="utf-8",
        )
        parser = _safe_read_ini(ini)
        issues = _validate_paths_in_ini(ini, parser)
        assert len(issues) == 1
        assert issues[0].severity == SEVERITY_WARN
        assert "Z:\\NonExistent" in issues[0].message

    def test_valid_path_no_issue(self, tmp_path):
        real_dir = tmp_path / "ExistingDir"
        real_dir.mkdir()
        ini = tmp_path / "test.ini"
        ini.write_text(
            f"[Paths]\nEmuPath={real_dir}\n",
            encoding="utf-8",
        )
        parser = _safe_read_ini(ini)
        issues = _validate_paths_in_ini(ini, parser)
        assert len(issues) == 0

    def test_non_path_values_ignored(self, tmp_path):
        ini = tmp_path / "test.ini"
        ini.write_text(
            "[Settings]\nEnabled=true\nCount=42\nUrl=http://localhost\n",
            encoding="utf-8",
        )
        parser = _safe_read_ini(ini)
        issues = _validate_paths_in_ini(ini, parser)
        assert len(issues) == 0


# ── Unit tests: data classes ────────────────────────────────────────

class TestDataClasses:
    def test_rl_issue_to_dict(self):
        issue = RLIssue(
            severity="error", category="test",
            message="broken", file="/path", section="S", key="K",
        )
        d = issue.to_dict()
        assert d["severity"] == "error"
        assert d["file"] == "/path"
        assert d["section"] == "S"

    def test_rl_issue_minimal(self):
        issue = RLIssue(severity="info", category="test", message="note")
        d = issue.to_dict()
        assert "file" not in d
        assert "section" not in d

    def test_module_info_to_dict(self):
        mod = ModuleInfo(name="RetroArch", path="/mods/RA", has_ahk=True, ahk_file="RA.ahk")
        d = mod.to_dict()
        assert d["name"] == "RetroArch"
        assert d["has_ahk"] is True

    def test_system_mapping_to_dict(self):
        m = SystemMapping(system_name="MAME", ini_path="/s/MAME.ini", emulator_name="MAME")
        d = m.to_dict()
        assert d["system_name"] == "MAME"
        assert d["emulator_name"] == "MAME"

    def test_report_to_dict_summary(self):
        report = RLValidationReport(rl_root="/rl")
        report.issues = [
            RLIssue(severity="error", category="t", message="e1"),
            RLIssue(severity="warn", category="t", message="w1"),
            RLIssue(severity="warn", category="t", message="w2"),
            RLIssue(severity="info", category="t", message="i1"),
        ]
        d = report.to_dict()
        assert d["summary"]["total_issues"] == 4
        assert d["summary"]["errors"] == 1
        assert d["summary"]["warnings"] == 2
        assert d["summary"]["info"] == 1


# ── Integration tests: validate_modules ─────────────────────────────

class TestValidateModules:
    def test_valid_modules(self, rl_tree):
        modules, issues = validate_modules(rl_tree)
        assert len(modules) == 3
        names = {m.name for m in modules}
        assert "RetroArch" in names
        assert "MAME" in names
        assert "Dolphin" in names
        for m in modules:
            assert m.has_ahk is True

    def test_missing_ahk(self, broken_rl_tree):
        modules, issues = validate_modules(broken_rl_tree)
        assert len(modules) == 1
        assert modules[0].name == "EmptyModule"
        assert modules[0].has_ahk is False
        ahk_issues = [i for i in issues if "no .ahk" in i.message.lower()]
        assert len(ahk_issues) == 1

    def test_no_modules_dir(self, tmp_path):
        rl = tmp_path / "RL"
        rl.mkdir()
        modules, issues = validate_modules(rl)
        assert len(modules) == 0
        assert any(i.severity == SEVERITY_ERROR for i in issues)


# ── Integration tests: validate_system_settings ─────────────────────

class TestValidateSystemSettings:
    def test_valid_systems(self, rl_tree):
        module_names = {"RetroArch", "MAME", "Dolphin"}
        mappings, issues = validate_system_settings(rl_tree, module_names)
        assert len(mappings) == 3
        names = {m.system_name for m in mappings}
        assert "MAME" in names

    def test_broken_module_reference(self, broken_rl_tree):
        module_names = {"EmptyModule"}
        mappings, issues = validate_system_settings(broken_rl_tree, module_names)
        ref_issues = [i for i in issues if i.category == "system_mapping"]
        assert len(ref_issues) == 1
        assert "NonExistentModule" in ref_issues[0].message

    def test_broken_paths(self, broken_rl_tree):
        mappings, issues = validate_system_settings(broken_rl_tree, set())
        path_issues = [i for i in issues if i.category == "system_settings"]
        assert len(path_issues) >= 1  # Q:\fake\roms is broken

    def test_no_settings_dir(self, tmp_path):
        rl = tmp_path / "RL"
        rl.mkdir()
        mappings, issues = validate_system_settings(rl)
        assert len(mappings) == 0
        assert any(i.severity == SEVERITY_ERROR for i in issues)


# ── Integration tests: validate_global_settings ─────────────────────

class TestValidateGlobalSettings:
    def test_valid_global(self, rl_tree):
        settings, issues = validate_global_settings(rl_tree)
        assert "sections" in settings
        assert settings["ini_path"].endswith("RocketLauncher.ini")

    def test_broken_paths_in_global(self, broken_rl_tree):
        settings, issues = validate_global_settings(broken_rl_tree)
        path_issues = [i for i in issues if "Path does not exist" in i.message]
        assert len(path_issues) >= 1

    def test_missing_global_ini(self, tmp_path):
        rl = tmp_path / "RL"
        rl.mkdir()
        (rl / "Settings").mkdir()
        settings, issues = validate_global_settings(rl)
        assert any(i.severity == SEVERITY_WARN for i in issues)


# ── Integration tests: validate_plugins ─────────────────────────────

class TestValidatePlugins:
    def test_valid_plugins(self, rl_tree):
        plugins, issues = validate_plugins(rl_tree)
        assert len(plugins) == 1
        assert plugins[0]["name"] == "Fade"
        assert plugins[0]["has_ahk"] is True

    def test_no_plugins_dir(self, tmp_path):
        rl = tmp_path / "RL"
        rl.mkdir()
        plugins, issues = validate_plugins(rl)
        assert len(plugins) == 0
        assert any(i.severity == SEVERITY_INFO for i in issues)


# ── Integration tests: validate_rl (full) ──────────────────────────

class TestValidateRL:
    @patch("engines.rl_config_validator.cfg_get")
    def test_full_valid_rl(self, mock_cfg, rl_tree):
        mock_cfg.return_value = str(rl_tree)
        report = validate_rl()
        assert report.rl_exists is True
        assert report.exe_exists is True
        assert report.module_count == 3
        assert report.system_count == 3
        assert report.plugin_count == 1
        assert report.health_score > 50.0

    def test_explicit_root(self, rl_tree):
        report = validate_rl(str(rl_tree))
        assert report.rl_exists is True
        assert report.health_score > 0

    @patch("engines.rl_config_validator.cfg_get")
    def test_broken_rl(self, mock_cfg, broken_rl_tree):
        mock_cfg.return_value = str(broken_rl_tree)
        report = validate_rl()
        assert report.rl_exists is True
        assert report.exe_exists is False
        errors = sum(1 for i in report.issues if i.severity == SEVERITY_ERROR)
        assert errors >= 1

    def test_nonexistent_root(self, tmp_path):
        report = validate_rl(str(tmp_path / "nope"))
        assert report.rl_exists is False
        assert report.health_score == 0.0
        assert len(report.issues) >= 1

    def test_report_to_dict(self, rl_tree):
        report = validate_rl(str(rl_tree))
        d = report.to_dict()
        assert "summary" in d
        assert "modules" in d
        assert "system_mappings" in d
        assert "plugins" in d
        assert isinstance(d["health_score"], float)


# ── Integration tests: validate_single_system ──────────────────────

class TestValidateSingleSystem:
    def test_existing_system(self, rl_tree):
        result = validate_single_system("MAME", str(rl_tree))
        assert result["settings_dir_exists"] is True
        assert result["ini_exists"] is True
        assert "sections" in result

    def test_missing_system(self, rl_tree):
        result = validate_single_system("NonExistent", str(rl_tree))
        assert result["settings_dir_exists"] is False
        assert result["ini_exists"] is False

    def test_nonexistent_rl_root(self, tmp_path):
        result = validate_single_system("MAME", str(tmp_path / "nope"))
        assert len(result["issues"]) >= 1


# ── Integration tests: find_orphaned_settings ──────────────────────

class TestFindOrphanedSettings:
    @patch("engines.rl_config_validator.cfg_get")
    def test_orphaned_detection(self, mock_cfg, rl_tree, tmp_path):
        # Create HyperSpin databases dir with only MAME
        db_root = tmp_path / "Databases"
        db_root.mkdir()
        (db_root / "MAME").mkdir()

        def side_effect(key, default=""):
            if "rocketlauncher" in key:
                return str(rl_tree)
            if "hyperspin" in key:
                return str(tmp_path)
            if "databases" in key:
                return str(db_root)
            return default

        mock_cfg.side_effect = side_effect
        result = find_orphaned_settings()
        # Systems in settings but not in DB: "Nintendo 64", "Sega Genesis"
        assert result["orphaned_count"] >= 2
        # Systems in DB but not in settings: none (MAME is in both)
        assert "MAME" not in result["orphaned_settings"]

    def test_nonexistent_root(self, tmp_path):
        result = find_orphaned_settings(str(tmp_path / "nope"))
        assert result["orphaned_settings"] == []


# ── Integration tests: rl_summary ──────────────────────────────────

class TestRLSummary:
    def test_summary(self, rl_tree):
        result = rl_summary(str(rl_tree))
        assert "health_score" in result
        assert "module_count" in result
        assert result["exists"] is True
        assert result["module_count"] == 3


# ── Health score tests ──────────────────────────────────────────────

class TestHealthScore:
    def test_perfect_score(self):
        report = RLValidationReport(rl_root="/rl")
        report.rl_exists = True
        report.exe_exists = True
        report.global_ini_valid = True
        report.module_count = 15
        report.system_count = 20
        report.plugin_count = 3
        report.issues = []
        score = _compute_health_score(report)
        assert score == 100.0

    def test_zero_score(self):
        report = RLValidationReport(rl_root="/rl")
        report.rl_exists = False
        report.exe_exists = False
        report.global_ini_valid = False
        report.module_count = 0
        report.system_count = 0
        report.plugin_count = 0
        report.issues = [
            RLIssue(severity=SEVERITY_ERROR, category="t", message="e")
            for _ in range(5)
        ]
        score = _compute_health_score(report)
        assert score == 0.0

    def test_deductions(self):
        report = RLValidationReport(rl_root="/rl")
        report.rl_exists = True
        report.exe_exists = True
        report.global_ini_valid = True
        report.module_count = 5
        report.system_count = 5
        report.plugin_count = 1
        report.issues = [
            RLIssue(severity=SEVERITY_ERROR, category="t", message="e1"),
            RLIssue(severity=SEVERITY_WARN, category="t", message="w1"),
            RLIssue(severity=SEVERITY_WARN, category="t", message="w2"),
        ]
        score = _compute_health_score(report)
        # 20+20+15+10+15+10 = 90, minus 5 (error) - 2 (warns) = 83
        assert score == 83.0

    def test_score_clamped_at_zero(self):
        report = RLValidationReport(rl_root="/rl")
        report.issues = [
            RLIssue(severity=SEVERITY_ERROR, category="t", message=f"e{i}")
            for i in range(30)
        ]
        score = _compute_health_score(report)
        assert score == 0.0
