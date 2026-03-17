"""Tests for M11 — Update Applier engine."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestListTrackedEmulators(unittest.TestCase):
    @patch("engines.update_applier.cfg_get", return_value="C:\\Emulators")
    def test_returns_list(self, _cfg):
        from engines.update_applier import list_tracked_emulators
        result = list_tracked_emulators()
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        first = result[0]
        self.assertIn("emulator", first)
        self.assertIn("installed", first)
        self.assertIn("github", first)


class TestCheckUpdates(unittest.TestCase):
    @patch("engines.update_applier.check_updates")
    def test_check_updates_structure(self, mock_check):
        mock_check.return_value = {
            "checked": 1,
            "updates_available": 0,
            "emulators": [{"emulator": "MAME", "update_available": False}],
        }
        result = mock_check()
        self.assertIn("checked", result)
        self.assertIn("updates_available", result)
        self.assertIn("emulators", result)

    def test_check_updates_unknown_emulator(self):
        from engines.update_applier import check_updates
        with patch("engines.release_checker.check_single_emulator", return_value=None):
            result = check_updates("NonExistentEmu9999")
            self.assertIn("error", result)


class TestDownloadEmulatorUpdate(unittest.TestCase):
    def test_download_no_url(self):
        from engines.update_applier import download_emulator_update
        with patch("engines.release_checker.check_single_emulator", return_value=None):
            result = download_emulator_update("FakeEmu")
            self.assertEqual(result["status"], "download_failed") if "status" in result else self.assertIn("error", result)


class TestApplyUpdate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a fake emulator dir
        self.emu_dir = os.path.join(self.tmpdir, "Emulators", "MAME")
        os.makedirs(self.emu_dir)
        # Create a fake update source
        self.source_dir = os.path.join(self.tmpdir, "update_src")
        os.makedirs(self.source_dir)
        Path(os.path.join(self.source_dir, "mame.exe")).write_text("fake")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_apply_unknown_emulator(self):
        from engines.update_applier import apply_update
        result = apply_update("UnknownEmu999", self.source_dir)
        self.assertIn("error", result)

    def test_apply_missing_source(self):
        from engines.update_applier import apply_update
        result = apply_update("MAME", "/nonexistent/path/to/update")
        self.assertIn("error", result)

    def test_apply_dry_run(self):
        """Dry run should snapshot but not apply."""
        from engines.update_applier import apply_update

        mock_pipeline = MagicMock()
        mock_pipeline.register.return_value = 42
        mock_pipeline.snapshot.return_value = Path(self.tmpdir) / "snap"

        with patch("engines.update_manager.UpdatePipeline", return_value=mock_pipeline), \
             patch("engines.update_applier.cfg_get", return_value=os.path.join(self.tmpdir, "Emulators")), \
             patch("engines.release_checker.detect_local_version", return_value="0.260"):
            result = apply_update("MAME", self.source_dir, dry_run=True)
            self.assertEqual(result["status"], "dry_run")
            mock_pipeline.apply.assert_not_called()


class TestRollbackUpdate(unittest.TestCase):
    @patch("engines.update_applier.db")
    def test_rollback_not_found(self, mock_db):
        mock_db.execute.return_value = []
        from engines.update_applier import rollback_update
        result = rollback_update(99999)
        self.assertIn("error", result)


class TestGetUpdateStatus(unittest.TestCase):
    @patch("engines.update_manager.get_update_queue", return_value=[])
    @patch("engines.update_manager.get_update_history", return_value=[])
    def test_status_structure(self, _hist, _queue):
        from engines.update_applier import get_update_status
        result = get_update_status()
        self.assertIn("pending", result)
        self.assertIn("queue", result)
        self.assertIn("history", result)


if __name__ == "__main__":
    unittest.main()
