"""Tests for M12 — Emulator Version Tracker & Updater."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.version_tracker import (
    _parse_version,
    version_compare,
    is_update_available,
    scan_emulator_versions,
    get_version_history,
    get_all_tracked,
    get_outdated,
    stage_update,
    list_quarantine,
    reject_quarantine,
    apply_staged_update,
    tracker_summary,
    ensure_tables,
)


class TestVersionParsing(unittest.TestCase):
    def test_simple_semver(self):
        self.assertEqual(_parse_version("1.2.3"), (1, 2, 3))

    def test_two_part(self):
        self.assertEqual(_parse_version("0.268"), (0, 268))

    def test_leading_v(self):
        self.assertEqual(_parse_version("v2.3.1"), (2, 3, 1))

    def test_mame_style(self):
        self.assertEqual(_parse_version("mame0268"), (268,))

    def test_unknown(self):
        self.assertEqual(_parse_version("unknown"), (0,))

    def test_empty(self):
        self.assertEqual(_parse_version(""), (0,))

    def test_beta_suffix(self):
        self.assertEqual(_parse_version("1.5.0-beta2"), (1, 5, 0))


class TestVersionCompare(unittest.TestCase):
    def test_equal(self):
        self.assertEqual(version_compare("1.2.3", "1.2.3"), 0)

    def test_older(self):
        self.assertEqual(version_compare("1.2.3", "1.3.0"), -1)

    def test_newer(self):
        self.assertEqual(version_compare("2.0.0", "1.9.9"), 1)

    def test_different_lengths(self):
        self.assertEqual(version_compare("1.2", "1.2.1"), -1)

    def test_mame_versions(self):
        self.assertEqual(version_compare("0267", "0268"), -1)


class TestIsUpdateAvailable(unittest.TestCase):
    def test_update_available(self):
        self.assertTrue(is_update_available("1.0.0", "1.1.0"))

    def test_no_update(self):
        self.assertFalse(is_update_available("1.1.0", "1.1.0"))

    def test_unknown_local(self):
        self.assertTrue(is_update_available("unknown", "1.0.0"))

    def test_empty_remote(self):
        self.assertFalse(is_update_available("1.0.0", ""))


class TestScanEmulatorVersions(unittest.TestCase):
    @patch("engines.version_tracker.cfg_get", return_value="")
    def test_missing_root(self, _cfg):
        result = scan_emulator_versions("/nonexistent/path")
        self.assertTrue(any("error" in r for r in result))

    @patch("engines.version_tracker.db")
    @patch("engines.version_tracker.cfg_get", return_value="")
    def test_empty_root(self, _cfg, _db):
        with tempfile.TemporaryDirectory() as tmp:
            result = scan_emulator_versions(tmp)
            self.assertEqual(result, [])


class TestGetVersionHistory(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = [{"version": "1.0"}]
        result = get_version_history("MAME")
        self.assertIsInstance(result, list)


class TestGetAllTracked(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = [{"name": "MAME", "version": "0.268"}]
        result = get_all_tracked()
        self.assertIsInstance(result, list)


class TestStageUpdate(unittest.TestCase):
    @patch("engines.version_tracker.ensure_tables")
    def test_unknown_emulator(self, _et):
        result = stage_update("FakeEmulator999")
        self.assertIn("error", result)

    @patch("engines.version_tracker.ensure_tables")
    @patch("engines.release_checker.check_single_emulator", return_value=None)
    def test_no_release(self, _check, _et):
        result = stage_update("MAME")
        self.assertIn("error", result)


class TestListQuarantine(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = []
        result = list_quarantine()
        self.assertIsInstance(result, list)


class TestRejectQuarantine(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_not_found(self, mock_db):
        mock_db.execute.return_value = []
        result = reject_quarantine(99999)
        self.assertIn("error", result)


class TestApplyStagedUpdate(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_not_found(self, mock_db):
        mock_db.execute.return_value = []
        result = apply_staged_update(99999)
        self.assertIn("error", result)

    @patch("engines.version_tracker.db")
    def test_wrong_status(self, mock_db):
        mock_db.execute.return_value = [{"status": "applied", "emulator_name": "MAME",
                                          "filepath": "/tmp/x", "sha256": "abc"}]
        result = apply_staged_update(1)
        self.assertIn("error", result)
        self.assertIn("status", result["error"])


class TestTrackerSummary(unittest.TestCase):
    @patch("engines.version_tracker.db")
    def test_summary_structure(self, mock_db):
        mock_db.execute.side_effect = [
            [{"cnt": 10}],  # emulators count
            [{"cnt": 25}],  # versions count
            [{"cnt": 2}],   # quarantined count
            [],              # recent changes
        ]
        result = tracker_summary()
        self.assertIn("tracked_emulators", result)
        self.assertIn("total_version_records", result)
        self.assertIn("quarantined_updates", result)
        self.assertEqual(result["tracked_emulators"], 10)


if __name__ == "__main__":
    unittest.main()
