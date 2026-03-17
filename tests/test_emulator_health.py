"""Tests for M7 — Emulator Health Check engine (engines/emulator_health.py)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_emu_dir(tmp_path: Path, name: str, exe_name: str | None = None,
                  ini_content: str | None = None) -> Path:
    """Create a fake emulator directory with optional exe and INI config."""
    emu_dir = tmp_path / name
    emu_dir.mkdir(parents=True)
    if exe_name:
        exe = emu_dir / exe_name
        exe.write_bytes(b"\x00" * 200 * 1024)  # 200 KB fake exe
    if ini_content is not None:
        ini = emu_dir / f"{name}.ini"
        ini.write_text(ini_content, encoding="utf-8")
    return emu_dir


def _make_rl_modules(tmp_path: Path, *module_names: str) -> Path:
    """Create a fake RocketLauncher Modules directory."""
    rl_root = tmp_path / "RocketLauncher"
    modules = rl_root / "Modules"
    modules.mkdir(parents=True)
    for name in module_names:
        (modules / name).mkdir()
    return str(rl_root)


# ---------------------------------------------------------------------------
# Unit tests for internal helpers
# ---------------------------------------------------------------------------

class TestVersionFromDirname:
    def test_dotted_version(self):
        from engines.emulator_health import _version_from_dirname
        assert _version_from_dirname("MAME 0.268") == "0.268"

    def test_compact_mame_version(self):
        from engines.emulator_health import _version_from_dirname
        assert _version_from_dirname("mame0268") == "0268"

    def test_no_version(self):
        from engines.emulator_health import _version_from_dirname
        assert _version_from_dirname("RetroArch") == "unknown"

    def test_semver(self):
        from engines.emulator_health import _version_from_dirname
        assert _version_from_dirname("Dolphin-5.0.21264") == "5.0.21264"


class TestFindExe:
    def test_finds_known_exe(self, tmp_path):
        from engines.emulator_health import _find_exe
        emu_dir = _make_emu_dir(tmp_path, "MAME", exe_name="mame.exe")
        path, size = _find_exe(emu_dir)
        assert "mame.exe" in path
        assert size > 0

    def test_fallback_largest_exe(self, tmp_path):
        from engines.emulator_health import _find_exe
        emu_dir = tmp_path / "UnknownEmu"
        emu_dir.mkdir()
        small = emu_dir / "small.exe"
        large = emu_dir / "large.exe"
        small.write_bytes(b"\x00" * 50)
        large.write_bytes(b"\x00" * 500)
        path, size = _find_exe(emu_dir)
        assert "large.exe" in path
        assert size == 500

    def test_no_exe_returns_empty(self, tmp_path):
        from engines.emulator_health import _find_exe
        emu_dir = tmp_path / "NoExe"
        emu_dir.mkdir()
        path, size = _find_exe(emu_dir)
        assert path == ""
        assert size == 0


class TestCheckConfigs:
    def test_no_issues_clean_ini(self, tmp_path):
        from engines.emulator_health import _check_configs
        emu_dir = tmp_path / "CleanEmu"
        emu_dir.mkdir()
        ini = emu_dir / "clean.ini"
        ini.write_text("[Settings]\nfullscreen=1\n", encoding="utf-8")
        configs, issues = _check_configs(emu_dir)
        assert len(configs) >= 1
        assert issues == []

    def test_detects_broken_path_in_ini(self, tmp_path):
        from engines.emulator_health import _check_configs
        emu_dir = tmp_path / "BrokenEmu"
        emu_dir.mkdir()
        ini = emu_dir / "broken.ini"
        ini.write_text(
            "[Settings]\nrom_path=Z:\\NonExistentPath\\roms\n",
            encoding="utf-8",
        )
        configs, issues = _check_configs(emu_dir)
        assert len(issues) >= 1
        assert "path missing" in issues[0]

    def test_no_configs(self, tmp_path):
        from engines.emulator_health import _check_configs
        emu_dir = tmp_path / "EmptyEmu"
        emu_dir.mkdir()
        configs, issues = _check_configs(emu_dir)
        assert configs == []
        assert issues == []


class TestCheckRLModule:
    def test_finds_exact_module(self, tmp_path):
        from engines.emulator_health import _check_rl_module
        rl_root = _make_rl_modules(tmp_path, "MAME", "RetroArch")
        found, path = _check_rl_module("MAME", rl_root)
        assert found is True
        assert "MAME" in path

    def test_finds_fuzzy_module(self, tmp_path):
        from engines.emulator_health import _check_rl_module
        rl_root = _make_rl_modules(tmp_path, "MAME 2003")
        found, path = _check_rl_module("MAME", rl_root)
        assert found is True

    def test_module_not_found(self, tmp_path):
        from engines.emulator_health import _check_rl_module
        rl_root = _make_rl_modules(tmp_path, "Dolphin")
        found, path = _check_rl_module("PCSX2", rl_root)
        assert found is False
        assert path == ""

    def test_no_rl_root(self):
        from engines.emulator_health import _check_rl_module
        found, path = _check_rl_module("MAME", "")
        assert found is False
        assert path == ""

    def test_nonexistent_rl_root(self):
        from engines.emulator_health import _check_rl_module
        found, path = _check_rl_module("MAME", "Z:\\NoSuchDir")
        assert found is False


class TestScoreHealth:
    def test_perfect_score(self, tmp_path):
        from engines.emulator_health import EmulatorHealth, _score_health
        h = EmulatorHealth(
            name="MAME", path=str(tmp_path),
            exe_exists=True, exe_size_bytes=5 * 1024 * 1024,
            version="0.268",
            config_files=["mame.ini"],
            config_issues=[],
            rl_module_exists=True,
        )
        assert _score_health(h) == 100.0

    def test_no_exe_score(self, tmp_path):
        from engines.emulator_health import EmulatorHealth, _score_health
        h = EmulatorHealth(name="Bad", path=str(tmp_path), exe_exists=False)
        assert _score_health(h) < 50.0

    def test_exe_only_score(self, tmp_path):
        from engines.emulator_health import EmulatorHealth, _score_health
        h = EmulatorHealth(
            name="MinEmu", path=str(tmp_path),
            exe_exists=True, exe_size_bytes=200 * 1024,
            version="unknown", config_files=[], config_issues=[],
            rl_module_exists=False,
        )
        score = _score_health(h)
        # exe(50) + size(10) + no cfg issues(10) = 70
        assert score == 70.0


# ---------------------------------------------------------------------------
# Integration: check_emulator
# ---------------------------------------------------------------------------

class TestCheckEmulator:
    def test_healthy_emulator(self, tmp_path):
        from engines.emulator_health import check_emulator
        emu_dir = _make_emu_dir(tmp_path, "MAME", exe_name="mame.exe")
        rl_root = _make_rl_modules(tmp_path, "MAME")
        result = check_emulator(emu_dir, rl_root=rl_root)
        assert result.exe_exists is True
        assert result.rl_module_exists is True
        assert result.health_score >= 60.0
        assert result.is_healthy is True

    def test_missing_exe(self, tmp_path):
        from engines.emulator_health import check_emulator
        emu_dir = tmp_path / "NoExeEmu"
        emu_dir.mkdir()
        result = check_emulator(emu_dir)
        assert result.exe_exists is False
        assert result.is_healthy is False
        assert result.health_score < 60.0
        assert any(i["severity"] == "warn" for i in result.issues)

    def test_nonexistent_directory(self, tmp_path):
        from engines.emulator_health import check_emulator
        ghost = tmp_path / "GhostEmu"
        result = check_emulator(ghost)
        assert result.exe_exists is False
        assert result.is_healthy is False
        assert any(i["severity"] == "error" for i in result.issues)

    def test_to_dict_keys(self, tmp_path):
        from engines.emulator_health import check_emulator
        emu_dir = _make_emu_dir(tmp_path, "TestEmu", exe_name="test.exe")
        d = check_emulator(emu_dir).to_dict()
        for key in ("name", "path", "exe_path", "exe_exists", "exe_size_bytes",
                    "version", "is_healthy", "health_score",
                    "config_files", "config_issues", "rl_module_exists",
                    "rl_module_path", "issues"):
            assert key in d, f"Missing key: {key}"

    def test_broken_ini_creates_issue(self, tmp_path):
        from engines.emulator_health import check_emulator
        emu_dir = _make_emu_dir(
            tmp_path, "BrokenIni", exe_name="emu.exe",
            ini_content="[Paths]\nroms=Z:\\Missing\\roms\n",
        )
        result = check_emulator(emu_dir)
        assert len(result.config_issues) >= 1


# ---------------------------------------------------------------------------
# Integration: check_all_emulators / health_summary
# ---------------------------------------------------------------------------

class TestHealthSummary:
    def test_empty_root(self, tmp_path):
        from engines.emulator_health import health_summary
        result = health_summary(emu_root=str(tmp_path))
        assert result["total"] == 0
        assert result["healthy"] == 0
        assert result["unhealthy"] == 0
        assert result["avg_health_score"] == 0.0

    def test_summary_with_one_healthy(self, tmp_path):
        from engines.emulator_health import health_summary
        _make_emu_dir(tmp_path, "MAME", exe_name="mame.exe")
        rl_root = _make_rl_modules(tmp_path, "MAME")
        result = health_summary(emu_root=str(tmp_path), rl_root=rl_root)
        assert result["total"] >= 1
        assert result["healthy"] >= 1
        assert "emulators" in result
        assert "critical_issues" in result

    def test_summary_keys(self, tmp_path):
        from engines.emulator_health import health_summary
        result = health_summary(emu_root=str(tmp_path))
        for key in ("total", "healthy", "unhealthy", "avg_health_score",
                    "emulators", "critical_issues"):
            assert key in result

    def test_missing_emu_root(self, tmp_path):
        from engines.emulator_health import health_summary
        result = health_summary(emu_root=str(tmp_path / "does_not_exist"))
        assert result["total"] == 0

    def test_check_single_by_path(self, tmp_path):
        from engines.emulator_health import check_single_emulator
        emu_dir = _make_emu_dir(tmp_path, "SingleTest", exe_name="test.exe")
        result = check_single_emulator(str(emu_dir))
        assert result["name"] == "SingleTest"
        assert result["exe_exists"] is True

    def test_check_single_missing_returns_error(self, tmp_path):
        from engines.emulator_health import check_single_emulator
        result = check_single_emulator(str(tmp_path / "Ghost"))
        assert "error" in result
