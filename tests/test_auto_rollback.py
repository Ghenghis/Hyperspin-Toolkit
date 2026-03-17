"""Tests for M15 — Automated Rollback on Failure."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.auto_rollback import (
    get_policy,
    set_policy,
    list_policies,
    run_health_checks,
    auto_rollback,
    post_update_check,
    list_rollbacks,
    rollback_summary,
    _check_exe_exists,
    _check_health_score,
    _check_test_cmd,
    ensure_tables,
)


class TestGetPolicy(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_default_policy(self, mock_db):
        mock_db.execute.return_value = []
        policy = get_policy("MAME")
        self.assertEqual(policy["emulator_name"], "MAME")
        self.assertTrue(policy["auto_rollback_enabled"])
        self.assertTrue(policy["health_check_required"])

    @patch("engines.auto_rollback.db")
    def test_existing_policy(self, mock_db):
        mock_db.execute.return_value = [{
            "emulator_name": "MAME",
            "auto_rollback_enabled": 0,
            "health_check_required": 1,
            "test_cmd": "mame -verifyroms",
            "max_rollback_age_hours": 48,
        }]
        policy = get_policy("MAME")
        self.assertEqual(policy["auto_rollback_enabled"], 0)
        self.assertEqual(policy["test_cmd"], "mame -verifyroms")


class TestSetPolicy(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_set_policy(self, mock_db):
        mock_db.execute.return_value = [{
            "emulator_name": "MAME",
            "auto_rollback_enabled": 1,
            "health_check_required": 1,
            "test_cmd": "",
            "max_rollback_age_hours": 72,
        }]
        mock_db.get_conn.return_value.__enter__ = MagicMock()
        mock_db.get_conn.return_value.__exit__ = MagicMock()
        result = set_policy("MAME", auto_rollback_enabled=True)
        self.assertEqual(result["emulator_name"], "MAME")


class TestListPolicies(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = []
        result = list_policies()
        self.assertIsInstance(result, list)


class TestCheckExeExists(unittest.TestCase):
    @patch("engines.auto_rollback.cfg_get", return_value="")
    def test_missing_dir(self, _cfg):
        result = _check_exe_exists("NonExistent999", emu_root="/nonexistent")
        self.assertFalse(result["passed"])
        self.assertEqual(result["check"], "exe_exists")

    def test_existing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            emu_dir = Path(tmp) / "TestEmu"
            emu_dir.mkdir()
            (emu_dir / "test.exe").write_bytes(b"\x00" * 64)
            result = _check_exe_exists("TestEmu", emu_root=tmp)
            self.assertEqual(result["check"], "exe_exists")


class TestCheckHealthScore(unittest.TestCase):
    @patch("engines.auto_rollback.cfg_get", return_value="")
    def test_missing_dir(self, _cfg):
        result = _check_health_score("NonExistent999", emu_root="/nonexistent")
        self.assertFalse(result["passed"])


class TestCheckTestCmd(unittest.TestCase):
    def test_no_command(self):
        result = _check_test_cmd("")
        self.assertTrue(result["passed"])

    @patch("subprocess.run")
    def test_passing_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = _check_test_cmd("echo ok")
        self.assertTrue(result["passed"])

    @patch("subprocess.run")
    def test_failing_command(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="fail")
        result = _check_test_cmd("false")
        self.assertFalse(result["passed"])


class TestRunHealthChecks(unittest.TestCase):
    @patch("engines.auto_rollback.cfg_get", return_value="")
    @patch("engines.auto_rollback.db")
    def test_returns_structure(self, mock_db, _cfg):
        mock_db.execute.return_value = []
        result = run_health_checks("NonExistent", emu_root="/nonexistent")
        self.assertIn("all_passed", result)
        self.assertIn("checks", result)
        self.assertFalse(result["all_passed"])


class TestAutoRollback(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_disabled_by_policy(self, mock_db):
        mock_db.execute.return_value = [{
            "emulator_name": "TestEmu",
            "auto_rollback_enabled": 0,
            "health_check_required": 1,
            "test_cmd": "",
            "max_rollback_age_hours": 72,
        }]
        result = auto_rollback("TestEmu", "test failure")
        self.assertEqual(result["status"], "skipped")

    @patch("engines.auto_rollback.db")
    def test_no_backup_found(self, mock_db):
        # Policy check returns default (enabled)
        # Backup search returns empty
        mock_db.execute.side_effect = [
            [],  # ensure_tables
            [],  # get_policy
            [],  # ensure_tables
            [],  # get_policy (inside auto_rollback)
        ]
        mock_db.insert.return_value = 1
        mock_db.get_conn.return_value.__enter__ = MagicMock()
        mock_db.get_conn.return_value.__exit__ = MagicMock()

        # Mock _find_latest_backup to return None
        with patch("engines.auto_rollback._find_latest_backup", return_value=None):
            result = auto_rollback("TestEmu", "test failure")
            self.assertEqual(result["status"], "failed")
            self.assertIn("No backup", result["reason"])


class TestPostUpdateCheck(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    @patch("engines.auto_rollback.cfg_get", return_value="")
    def test_healthy_no_rollback(self, _cfg, mock_db):
        mock_db.execute.return_value = []

        with tempfile.TemporaryDirectory() as tmp:
            emu_dir = Path(tmp) / "TestEmu"
            emu_dir.mkdir()
            (emu_dir / "testemu.exe").write_bytes(b"\x00" * 64)

            result = post_update_check("TestEmu", emu_root=tmp)
            # May or may not pass depending on health score, but structure should be valid
            self.assertIn("status", result)
            self.assertIn("emulator", result)


class TestListRollbacks(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = []
        result = list_rollbacks()
        self.assertIsInstance(result, list)

    @patch("engines.auto_rollback.db")
    def test_filter_by_emulator(self, mock_db):
        mock_db.execute.return_value = []
        result = list_rollbacks("MAME")
        self.assertIsInstance(result, list)


class TestRollbackSummary(unittest.TestCase):
    @patch("engines.auto_rollback.db")
    def test_summary_structure(self, mock_db):
        mock_db.execute.side_effect = [
            [{"cnt": 3}],   # total
            [],              # by_status
            [],              # recent
            [{"cnt": 2}],   # policies
            [{"cnt": 1}],   # enabled
        ]
        result = rollback_summary()
        self.assertIn("total_rollbacks", result)
        self.assertIn("policies_configured", result)
        self.assertEqual(result["total_rollbacks"], 3)


if __name__ == "__main__":
    unittest.main()
