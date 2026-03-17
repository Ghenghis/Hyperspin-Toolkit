"""Tests for the HyperSpin Settings Manager (engines/hyperspin_settings.py).

Covers:
  - INI reading and writing
  - Single setting get/set
  - Typed accessors (bool, int, float)
  - Main INI validation
  - System INI validation
  - Full settings audit
  - Preset application
  - System discovery
  - Dataclass serialization
"""

import configparser
import tempfile
from pathlib import Path

import pytest

from engines.hyperspin_settings import (
    MAIN_SECTIONS,
    PRESETS,
    SYSTEM_SECTIONS,
    SettingsAuditReport,
    SettingsValidation,
    apply_preset,
    audit_all_settings,
    get_bool,
    get_float,
    get_int,
    get_setting,
    get_system_exe_config,
    list_configured_systems,
    list_presets,
    read_ini,
    set_setting,
    validate_main_ini,
    validate_system_ini,
    write_ini,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_hs_root(tmp_path):
    """Create a mock HyperSpin directory structure."""
    hs = tmp_path / "HyperSpin"
    (hs / "Settings").mkdir(parents=True)
    (hs / "Media").mkdir()
    (hs / "Databases").mkdir()
    return hs


@pytest.fixture
def sample_main_ini(tmp_hs_root):
    """Create a sample HyperSpin.ini with basic settings."""
    ini_path = tmp_hs_root / "Settings" / "HyperSpin.ini"
    ini_path.write_text(
        "[Main]\n"
        "Menu_Mode=multi\n"
        "Exit_Action=exit\n"
        "Exit_Confirmation=yes\n"
        "\n"
        "[Resolution]\n"
        "FullScreen=true\n"
        "Width=1920\n"
        "Height=1080\n"
        "\n"
        "[Wheel]\n"
        "Alpha=0.5\n"
        "Speed=medium\n"
        "Style=normal\n"
        "\n"
        "[Sound]\n"
        "Master_Volume=80\n"
        "\n"
        "[Attract_Mode]\n"
        "Enabled=true\n"
        "Wait=30\n"
        "\n"
        "[Navigation]\n"
        "Use_Last_Game=true\n",
        encoding="utf-8",
    )
    return ini_path


@pytest.fixture
def sample_system_ini(tmp_hs_root):
    """Create a sample per-system INI (MAME.ini)."""
    ini_path = tmp_hs_root / "Settings" / "MAME.ini"
    ini_path.write_text(
        "[exe]\n"
        "Path=..\\emulators\\MAME\\mame.exe\n"
        "ROM_Path=..\\ROMs\\MAME\n"
        "UseRocketLauncher=true\n"
        "RocketLauncherPath=..\\RocketLauncher\\RocketLauncher.exe\n"
        "\n"
        "[Themes]\n"
        "Use_Parent_Themes=true\n"
        "Default_Theme=default\n"
        "\n"
        "[Wheel]\n"
        "Speed=fast\n",
        encoding="utf-8",
    )
    return ini_path


# ---------------------------------------------------------------------------
# read_ini / write_ini
# ---------------------------------------------------------------------------

class TestReadWriteIni:
    def test_read_valid_ini(self, sample_main_ini):
        data = read_ini(sample_main_ini)
        assert "Main" in data
        assert "Resolution" in data
        assert data["Main"]["menu_mode"] == "multi"

    def test_read_nonexistent(self, tmp_path):
        data = read_ini(tmp_path / "nonexistent.ini")
        assert data == {}

    def test_write_and_read_roundtrip(self, tmp_path):
        ini_path = tmp_path / "test.ini"
        data = {
            "Section1": {"key1": "value1", "key2": "value2"},
            "Section2": {"keyA": "10", "keyB": "true"},
        }
        assert write_ini(ini_path, data) is True
        assert ini_path.exists()

        read_back = read_ini(ini_path)
        assert read_back["Section1"]["key1"] == "value1"
        assert read_back["Section2"]["keya"] == "10"  # configparser lowercases keys

    def test_write_creates_parent_dirs(self, tmp_path):
        ini_path = tmp_path / "deep" / "nested" / "dir" / "test.ini"
        data = {"Test": {"key": "val"}}
        assert write_ini(ini_path, data) is True
        assert ini_path.exists()

    def test_read_unicode_bom(self, tmp_path):
        """HyperSpin INI files sometimes have UTF-8 BOM."""
        ini_path = tmp_path / "bom.ini"
        ini_path.write_bytes(b"\xef\xbb\xbf[Main]\nKey=Value\n")
        data = read_ini(ini_path)
        assert "Main" in data


# ---------------------------------------------------------------------------
# get_setting / set_setting
# ---------------------------------------------------------------------------

class TestGetSetSetting:
    def test_get_existing(self, sample_main_ini):
        val = get_setting(sample_main_ini, "Resolution", "fullscreen")
        assert val == "true"

    def test_get_missing_key(self, sample_main_ini):
        val = get_setting(sample_main_ini, "Resolution", "nonexistent", "default_val")
        assert val == "default_val"

    def test_get_missing_section(self, sample_main_ini):
        val = get_setting(sample_main_ini, "NonExistent", "key", "fallback")
        assert val == "fallback"

    def test_set_existing_key(self, sample_main_ini):
        assert set_setting(sample_main_ini, "Sound", "Master_Volume", "50") is True
        val = get_setting(sample_main_ini, "Sound", "master_volume")
        assert val == "50"

    def test_set_new_section(self, sample_main_ini):
        assert set_setting(sample_main_ini, "NewSection", "new_key", "new_val") is True
        val = get_setting(sample_main_ini, "NewSection", "new_key")
        assert val == "new_val"


# ---------------------------------------------------------------------------
# Typed accessors
# ---------------------------------------------------------------------------

class TestTypedAccessors:
    def test_get_bool_true(self, sample_main_ini):
        assert get_bool(sample_main_ini, "Resolution", "fullscreen") is True

    def test_get_bool_false(self, tmp_path):
        ini = tmp_path / "test.ini"
        write_ini(ini, {"Sec": {"key": "false"}})
        assert get_bool(ini, "Sec", "key") is False

    def test_get_bool_default(self, sample_main_ini):
        assert get_bool(sample_main_ini, "Nonexistent", "key", True) is True

    def test_get_int(self, sample_main_ini):
        assert get_int(sample_main_ini, "Sound", "master_volume") == 80

    def test_get_int_default(self, sample_main_ini):
        assert get_int(sample_main_ini, "Sound", "nonexistent", 42) == 42

    def test_get_float(self, sample_main_ini):
        assert get_float(sample_main_ini, "Wheel", "alpha") == 0.5

    def test_get_float_default(self, sample_main_ini):
        assert get_float(sample_main_ini, "Wheel", "nonexistent", 1.5) == 1.5


# ---------------------------------------------------------------------------
# validate_main_ini
# ---------------------------------------------------------------------------

class TestValidateMainIni:
    def test_valid_main_ini(self, sample_main_ini, tmp_hs_root):
        val = validate_main_ini(sample_main_ini, tmp_hs_root)
        assert val.exists is True
        assert val.sections_found > 0
        assert val.keys_found > 0
        assert val.health_score > 0

    def test_missing_main_ini(self, tmp_path):
        val = validate_main_ini(tmp_path / "nope.ini", tmp_path)
        assert val.exists is False
        assert val.health_score == 0.0
        assert len(val.issues) >= 1

    def test_bad_resolution(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Resolution": {"Width": "abc", "Height": "def"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("Invalid resolution" in i["msg"] for i in val.issues)

    def test_low_resolution_warning(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Resolution": {"Width": "320", "Height": "240"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("Very low resolution" in w["msg"] for w in val.warnings)

    def test_bad_wheel_alpha(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Wheel": {"Alpha": "not_a_number"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("Invalid Wheel Alpha" in i["msg"] for i in val.issues)

    def test_wheel_alpha_out_of_range(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Wheel": {"Alpha": "5.0"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("outside normal range" in w["msg"] for w in val.warnings)

    def test_bad_volume(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Sound": {"Master_Volume": "abc"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("Invalid Master_Volume" in i["msg"] for i in val.issues)

    def test_volume_out_of_range(self, tmp_hs_root):
        ini = tmp_hs_root / "Settings" / "HyperSpin.ini"
        write_ini(ini, {"Sound": {"Master_Volume": "200"}})
        val = validate_main_ini(ini, tmp_hs_root)
        assert any("outside 0-100" in w["msg"] for w in val.warnings)

    def test_validation_to_dict(self, sample_main_ini, tmp_hs_root):
        val = validate_main_ini(sample_main_ini, tmp_hs_root)
        d = val.to_dict()
        assert "filepath" in d
        assert "health_score" in d
        assert isinstance(d["issues"], list)


# ---------------------------------------------------------------------------
# validate_system_ini
# ---------------------------------------------------------------------------

class TestValidateSystemIni:
    def test_valid_system_ini(self, sample_system_ini, tmp_hs_root):
        settings_dir = tmp_hs_root / "Settings"
        val = validate_system_ini("MAME", settings_dir, tmp_hs_root)
        assert val.exists is True
        assert val.sections_found > 0

    def test_missing_system_ini(self, tmp_hs_root):
        settings_dir = tmp_hs_root / "Settings"
        val = validate_system_ini("NonExistent", settings_dir, tmp_hs_root)
        assert val.exists is False
        assert val.health_score == 50.0  # not fatal

    def test_rl_path_warning(self, tmp_hs_root):
        settings_dir = tmp_hs_root / "Settings"
        ini = settings_dir / "TestSys.ini"
        write_ini(ini, {"exe": {"UseRocketLauncher": "true", "RocketLauncherPath": ""}})
        val = validate_system_ini("TestSys", settings_dir, tmp_hs_root)
        assert any("RocketLauncherPath is empty" in w["msg"] for w in val.warnings)


# ---------------------------------------------------------------------------
# audit_all_settings
# ---------------------------------------------------------------------------

class TestAuditAllSettings:
    def test_full_audit(self, sample_main_ini, sample_system_ini, tmp_hs_root):
        report = audit_all_settings(tmp_hs_root)
        assert isinstance(report, SettingsAuditReport)
        assert report.main_ini.exists is True
        assert report.system_count >= 1
        assert "MAME" in report.systems

    def test_audit_empty_hs(self, tmp_path):
        hs = tmp_path / "empty_hs"
        hs.mkdir()
        (hs / "Settings").mkdir()
        report = audit_all_settings(hs)
        assert report.main_ini.exists is False
        assert report.system_count == 0

    def test_audit_to_dict(self, sample_main_ini, sample_system_ini, tmp_hs_root):
        report = audit_all_settings(tmp_hs_root)
        d = report.to_dict()
        assert "main_ini" in d
        assert "systems" in d
        assert isinstance(d["systems"], dict)


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

class TestPresets:
    def test_apply_performance(self, sample_main_ini):
        assert apply_preset(sample_main_ini, "performance") is True
        data = read_ini(sample_main_ini)
        assert data.get("Optimizer", {}).get("cpu_priority") == "high"

    def test_apply_quality(self, sample_main_ini):
        assert apply_preset(sample_main_ini, "quality") is True
        data = read_ini(sample_main_ini)
        assert data.get("Attract_Mode", {}).get("enabled") == "true"

    def test_apply_cabinet(self, sample_main_ini):
        assert apply_preset(sample_main_ini, "cabinet") is True
        data = read_ini(sample_main_ini)
        assert data.get("Main", {}).get("exit_action") == "none"

    def test_apply_unknown_preset(self, sample_main_ini):
        assert apply_preset(sample_main_ini, "nonexistent") is False

    def test_list_presets(self):
        presets = list_presets()
        assert "performance" in presets
        assert "quality" in presets
        assert "cabinet" in presets

    def test_preset_preserves_existing(self, sample_main_ini):
        """Preset should not overwrite keys not in the preset."""
        original_vol = get_setting(sample_main_ini, "Sound", "master_volume")
        apply_preset(sample_main_ini, "performance")
        after_vol = get_setting(sample_main_ini, "Sound", "master_volume")
        assert original_vol == after_vol


# ---------------------------------------------------------------------------
# System discovery
# ---------------------------------------------------------------------------

class TestSystemDiscovery:
    def test_list_configured_systems(self, sample_system_ini, tmp_hs_root):
        systems = list_configured_systems(tmp_hs_root)
        assert "MAME" in systems

    def test_list_excludes_main_ini(self, sample_main_ini, tmp_hs_root):
        systems = list_configured_systems(tmp_hs_root)
        assert "HyperSpin" not in systems

    def test_list_empty_settings(self, tmp_path):
        hs = tmp_path / "empty"
        hs.mkdir()
        systems = list_configured_systems(hs)
        assert systems == []

    def test_get_system_exe_config(self, sample_system_ini, tmp_hs_root):
        exe = get_system_exe_config("MAME", tmp_hs_root)
        assert "path" in exe or "Path" in exe
        assert "userocketlauncher" in exe or "UseRocketLauncher" in exe

    def test_get_exe_config_missing_system(self, tmp_hs_root):
        exe = get_system_exe_config("NonExistent", tmp_hs_root)
        assert exe == {}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_settings_validation_to_dict(self):
        v = SettingsValidation(filepath="/test", exists=True, health_score=85.0)
        d = v.to_dict()
        assert d["filepath"] == "/test"
        assert d["health_score"] == 85.0

    def test_settings_audit_report_to_dict(self):
        r = SettingsAuditReport(system_count=5)
        d = r.to_dict()
        assert d["system_count"] == 5
        assert isinstance(d["systems"], dict)
