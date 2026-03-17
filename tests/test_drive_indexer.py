"""Tests for Drive Indexer & Identification Engine."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.drive_indexer import (
    load_registry,
    save_registry,
    find_drive_by_serial,
    find_drive_by_tag,
    find_drive_by_letter,
    detect_collection_type,
    generate_drive_manifest,
    drive_summary,
)


SAMPLE_REGISTRY = {
    "_updated": "2026-03-17",
    "drives": [
        {
            "tag": "TEST_HYPERSPIN",
            "role": "testing",
            "label": "Test_Hyperspin_Test",
            "current_letter": "D",
            "serial": "7E0538EE1A62",
            "model": "ST12000N M0127",
            "capacity_gb": 11176,
            "health_status": "Warning",
            "collection_type": "HyperSpin + RocketLauncher",
        },
        {
            "tag": "PRIMARY_HYPERSPIN",
            "role": "active_primary",
            "label": "Hyperspin_12T",
            "current_letter": "I",
            "serial": "00000000471D",
            "model": "ST12000N M000J-2TY103",
            "capacity_gb": 11176,
            "health_status": "Healthy",
            "collection_type": "HyperSpin + RocketLauncher",
        },
    ],
    "system_drives": [
        {
            "tag": "OS_PRIMARY",
            "label": "Windows X-Lite",
            "current_letter": "C",
            "serial": "0000_0006_2401_0005",
            "model": "addlink M.2 NVMe",
            "capacity_gb": 3815,
        },
    ],
    "collection_types": {},
}


class TestLoadRegistry(unittest.TestCase):
    def test_load_nonexistent(self):
        result = load_registry("/nonexistent/path.json")
        self.assertIn("drives", result)
        self.assertEqual(result["drives"], [])

    def test_load_valid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(SAMPLE_REGISTRY, f)
            f.flush()
            path = f.name
        try:
            result = load_registry(path)
            self.assertEqual(len(result["drives"]), 2)
            self.assertEqual(result["drives"][0]["tag"], "TEST_HYPERSPIN")
        finally:
            Path(path).unlink(missing_ok=True)


class TestSaveRegistry(unittest.TestCase):
    def test_save_and_reload(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_registry(SAMPLE_REGISTRY, path)
            reloaded = load_registry(path)
            self.assertEqual(len(reloaded["drives"]), 2)
            self.assertIn("_updated", reloaded)
        finally:
            Path(path).unlink(missing_ok=True)


class TestFindDriveBySerial(unittest.TestCase):
    def test_found(self):
        result = find_drive_by_serial("7E0538EE1A62", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)
        self.assertEqual(result["tag"], "TEST_HYPERSPIN")

    def test_not_found(self):
        result = find_drive_by_serial("NONEXISTENT", SAMPLE_REGISTRY)
        self.assertIsNone(result)

    def test_system_drive(self):
        result = find_drive_by_serial("0000_0006_2401_0005", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)
        self.assertEqual(result["tag"], "OS_PRIMARY")


class TestFindDriveByTag(unittest.TestCase):
    def test_found(self):
        result = find_drive_by_tag("PRIMARY_HYPERSPIN", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)
        self.assertEqual(result["current_letter"], "I")

    def test_not_found(self):
        result = find_drive_by_tag("NONEXISTENT", SAMPLE_REGISTRY)
        self.assertIsNone(result)


class TestFindDriveByLetter(unittest.TestCase):
    def test_found(self):
        result = find_drive_by_letter("D", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)
        self.assertEqual(result["tag"], "TEST_HYPERSPIN")

    def test_colon_stripped(self):
        result = find_drive_by_letter("D:", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)

    def test_case_insensitive(self):
        result = find_drive_by_letter("d", SAMPLE_REGISTRY)
        self.assertIsNotNone(result)

    def test_not_found(self):
        result = find_drive_by_letter("Z", SAMPLE_REGISTRY)
        self.assertIsNone(result)


class TestDetectCollectionType(unittest.TestCase):
    def test_hyperspin_rl(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Arcade").mkdir()
            (Path(tmp) / "BACKUP FILES - HYPERSPIN & ROCKETLAUNCHER").mkdir()
            (Path(tmp) / "HyperSpin_Backups").mkdir()
            # Create enough subdirs in Arcade to look like systems
            for i in range(60):
                (Path(tmp) / "Arcade" / f"System_{i}").mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "HyperSpin + RocketLauncher")

    def test_batocera(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "roms").mkdir()
            (Path(tmp) / "bios").mkdir()
            (Path(tmp) / "themes").mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "Batocera")

    def test_core_type_r(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctr = Path(tmp) / "CORE - TYPE R"
            ctr.mkdir()
            for d in ["collections", "core", "launchers.windows", "layouts", "meta"]:
                (ctr / d).mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "CORE - TYPE R")

    def test_attract_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            arcade = Path(tmp) / "Arcade"
            arcade.mkdir()
            for d in ["collections", "emulators", "layouts", "plugins"]:
                (arcade / d).mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "HyperSpin Attract Mode")

    def test_rom_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Games").mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "ROM Backup / PC Games")

    def test_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "random_folder").mkdir()
            result = detect_collection_type(tmp)
            self.assertEqual(result, "Unknown")

    def test_nonexistent(self):
        result = detect_collection_type("/nonexistent/path")
        self.assertEqual(result, "Unknown")


class TestGenerateDriveManifest(unittest.TestCase):
    @patch("engines.drive_indexer.enumerate_volumes", return_value=[])
    def test_nonexistent_drive(self, _):
        result = generate_drive_manifest("Z")
        self.assertIn("error", result)

    @patch("engines.drive_indexer.enumerate_volumes", return_value=[])
    def test_manifest_structure(self, _):
        # Test with an existing drive letter (C: should always exist on Windows)
        result = generate_drive_manifest("C")
        self.assertIn("drive_letter", result)
        self.assertEqual(result["drive_letter"], "C")
        self.assertIn("top_level_dirs", result)
        self.assertIn("collection_type", result)


class TestDriveSummary(unittest.TestCase):
    @patch("engines.drive_indexer.enumerate_physical_disks", return_value=[])
    @patch("engines.drive_indexer.enumerate_volumes", return_value=[])
    @patch("engines.drive_indexer.get_disk_to_volume_map", return_value={})
    @patch("engines.drive_indexer.load_registry", return_value=SAMPLE_REGISTRY)
    def test_summary_structure(self, *_):
        result = drive_summary()
        self.assertIn("total_disks", result)
        self.assertIn("total_volumes", result)
        self.assertIn("gaming_drives", result)
        self.assertIn("warning_count", result)


if __name__ == "__main__":
    unittest.main()
