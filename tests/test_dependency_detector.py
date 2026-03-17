"""Tests for M13 — Dependency Conflict Detector."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.dependency_detector import (
    DllInfo,
    Conflict,
    scan_emulator_dlls,
    scan_all_dependencies,
    detect_conflicts,
    check_update_conflicts,
    dependency_report,
    dependency_summary,
    _suggest_resolution,
    KNOWN_RUNTIMES,
)


class TestDllInfo(unittest.TestCase):
    def test_to_dict(self):
        info = DllInfo(name="test.dll", path="/tmp/test.dll", size_bytes=1024,
                       version="1.0", runtime_name="Test", is_system=False)
        d = info.to_dict()
        self.assertEqual(d["name"], "test.dll")
        self.assertEqual(d["size_bytes"], 1024)
        self.assertEqual(d["runtime_name"], "Test")

    def test_defaults(self):
        info = DllInfo(name="x.dll", path="/tmp/x.dll")
        self.assertEqual(info.size_bytes, 0)
        self.assertEqual(info.version, "")
        self.assertFalse(info.is_system)


class TestConflict(unittest.TestCase):
    def test_to_dict(self):
        c = Conflict(dll_name="test.dll", severity="warning",
                     message="conflict found", emulators=["A", "B"],
                     versions=["v1", "v2"], resolution="fix it")
        d = c.to_dict()
        self.assertEqual(d["dll_name"], "test.dll")
        self.assertEqual(d["severity"], "warning")
        self.assertEqual(len(d["emulators"]), 2)


class TestScanEmulatorDlls(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_emulator_dlls(Path(tmp))
            self.assertEqual(result, [])

    def test_finds_known_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Create a fake known DLL
            dll_path = Path(tmp) / "vcruntime140.dll"
            dll_path.write_bytes(b"\x00" * 512)
            result = scan_emulator_dlls(Path(tmp))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "vcruntime140.dll")
            self.assertEqual(result[0].runtime_name, "Visual C++ 2015-2022 Redistributable")

    def test_finds_pattern_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll_path = Path(tmp) / "d3d11.dll"
            dll_path.write_bytes(b"\x00" * 256)
            result = scan_emulator_dlls(Path(tmp))
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].name, "d3d11.dll")

    def test_ignores_unknown_dlls(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll_path = Path(tmp) / "mygame_custom.dll"
            dll_path.write_bytes(b"\x00" * 128)
            result = scan_emulator_dlls(Path(tmp))
            self.assertEqual(result, [])

    def test_nonexistent_dir(self):
        result = scan_emulator_dlls(Path("/nonexistent/dir"))
        self.assertEqual(result, [])


class TestScanAllDependencies(unittest.TestCase):
    @patch("engines.dependency_detector.cfg_get", return_value="")
    def test_missing_root(self, _cfg):
        result = scan_all_dependencies("/nonexistent/path")
        self.assertEqual(result, {})

    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_all_dependencies(tmp)
            self.assertEqual(result, {})

    def test_scans_subdirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            emu_dir = Path(tmp) / "MAME"
            emu_dir.mkdir()
            (emu_dir / "sdl2.dll").write_bytes(b"\x00" * 100)
            result = scan_all_dependencies(tmp)
            self.assertIn("MAME", result)
            self.assertEqual(len(result["MAME"]), 1)


class TestDetectConflicts(unittest.TestCase):
    def test_no_conflicts(self):
        dep_map = {
            "EmuA": [DllInfo("vcruntime140.dll", "/a/vcruntime140.dll", size_bytes=1000)],
            "EmuB": [DllInfo("vcruntime140.dll", "/b/vcruntime140.dll", size_bytes=1000)],
        }
        conflicts = detect_conflicts(dep_map)
        self.assertEqual(len(conflicts), 0)

    def test_size_conflict(self):
        dep_map = {
            "EmuA": [DllInfo("vcruntime140.dll", "/a/vcruntime140.dll", size_bytes=1000)],
            "EmuB": [DllInfo("vcruntime140.dll", "/b/vcruntime140.dll", size_bytes=2000)],
        }
        conflicts = detect_conflicts(dep_map)
        self.assertGreater(len(conflicts), 0)
        self.assertEqual(conflicts[0].dll_name, "vcruntime140.dll")
        self.assertEqual(conflicts[0].severity, "critical")

    def test_qt_mixing(self):
        dep_map = {
            "EmuA": [
                DllInfo("qt5core.dll", "/a/qt5core.dll", size_bytes=100),
                DllInfo("qt6core.dll", "/a/qt6core.dll", size_bytes=200),
            ],
        }
        conflicts = detect_conflicts(dep_map)
        qt_conflicts = [c for c in conflicts if "Qt" in c.dll_name]
        self.assertGreater(len(qt_conflicts), 0)

    def test_single_emulator_no_conflict(self):
        dep_map = {
            "EmuA": [DllInfo("sdl2.dll", "/a/sdl2.dll", size_bytes=500)],
        }
        conflicts = detect_conflicts(dep_map)
        self.assertEqual(len(conflicts), 0)


class TestSuggestResolution(unittest.TestCase):
    def test_vcpp(self):
        entries = [("A", DllInfo("vcruntime140.dll", "/a/v.dll", size_bytes=100))]
        res = _suggest_resolution("vcruntime140.dll", entries)
        self.assertIn("Visual C++", res)

    def test_directx(self):
        entries = [("A", DllInfo("d3d9.dll", "/a/d.dll", size_bytes=100))]
        res = _suggest_resolution("d3d9.dll", entries)
        self.assertIn("DirectX", res)

    def test_sdl(self):
        entries = [("A", DllInfo("sdl2.dll", "/a/s.dll", size_bytes=100))]
        res = _suggest_resolution("sdl2.dll", entries)
        self.assertIn("SDL", res)

    def test_unknown(self):
        entries = [("A", DllInfo("custom.dll", "/a/c.dll", size_bytes=100))]
        res = _suggest_resolution("custom.dll", entries)
        self.assertIn("own copy", res)


class TestCheckUpdateConflicts(unittest.TestCase):
    @patch("engines.dependency_detector.cfg_get", return_value="")
    def test_missing_emulator(self, _cfg):
        result = check_update_conflicts("NonExistent999", emu_root="/nonexistent")
        self.assertIn("error", result)

    def test_no_update_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            emu_dir = Path(tmp) / "MAME"
            emu_dir.mkdir()
            (emu_dir / "sdl2.dll").write_bytes(b"\x00" * 100)
            result = check_update_conflicts("MAME", emu_root=tmp)
            self.assertEqual(result["emulator"], "MAME")
            self.assertIn("changes", result)
            self.assertIn("safe_to_update", result)


class TestDependencyReport(unittest.TestCase):
    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dependency_report(tmp)
            self.assertEqual(result["emulators_scanned"], 0)
            self.assertEqual(result["total_shared_dlls"], 0)
            self.assertIn("conflicts", result)


class TestDependencySummary(unittest.TestCase):
    def test_empty_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = dependency_summary(tmp)
            self.assertEqual(result["emulators_scanned"], 0)
            self.assertIn("conflicts_total", result)


if __name__ == "__main__":
    unittest.main()
