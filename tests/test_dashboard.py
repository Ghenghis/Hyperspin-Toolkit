"""Dashboard smoke tests — REST endpoints, plugin routes, WebSocket.

Uses FastAPI TestClient to exercise all API endpoints without starting
a real server. Database calls are mocked where needed.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_config
load_config(PROJECT_ROOT / "config.yaml", reload=True)

from fastapi.testclient import TestClient
from dashboard.app import app


client = TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════════════
# Stats API
# ═══════════════════════════════════════════════════════════════════════

class TestStatsEndpoint(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_get_stats_ok(self, mock_db):
        mock_db.side_effect = [
            [{"cnt": 10}],   # systems
            [{"cnt": 500}],  # roms
            [{"cnt": 5}],    # emulators
            [{"cnt": 4}],    # healthy
            [{"cnt": 2}],    # backups
            [{"cnt": 1}],    # updates
            [{"avg_score": 75.0}],  # health score
        ]
        resp = client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total_systems"], 10)
        self.assertEqual(data["total_roms"], 500)
        self.assertEqual(data["total_emulators"], 5)
        self.assertEqual(data["healthy_emulators"], 4)
        self.assertEqual(data["avg_health_score"], 75.0)

    @patch("dashboard.app.db.execute", side_effect=Exception("DB offline"))
    def test_get_stats_db_error(self, mock_db):
        resp = client.get("/api/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)


# ═══════════════════════════════════════════════════════════════════════
# Systems API
# ═══════════════════════════════════════════════════════════════════════

class TestSystemsEndpoints(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_list_systems(self, mock_db):
        mock_db.return_value = [
            {"name": "MAME", "rom_count": 5000},
            {"name": "NES", "rom_count": 800},
        ]
        resp = client.get("/api/systems")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("systems", data)
        self.assertEqual(len(data["systems"]), 2)

    @patch("dashboard.app.db.execute")
    def test_system_detail_found(self, mock_db):
        mock_db.return_value = [{"name": "MAME", "rom_count": 5000}]
        resp = client.get("/api/systems/MAME")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["system"]["name"], "MAME")

    @patch("dashboard.app.db.execute")
    def test_system_detail_not_found(self, mock_db):
        mock_db.return_value = []
        resp = client.get("/api/systems/NonExistent")
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn("error", data)


# ═══════════════════════════════════════════════════════════════════════
# Emulators API
# ═══════════════════════════════════════════════════════════════════════

class TestEmulatorsEndpoint(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_list_emulators(self, mock_db):
        mock_db.return_value = [
            {"name": "MAME", "is_healthy": 1},
            {"name": "RetroArch", "is_healthy": 1},
        ]
        resp = client.get("/api/emulators")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("emulators", data)
        self.assertEqual(len(data["emulators"]), 2)


# ═══════════════════════════════════════════════════════════════════════
# Backups API
# ═══════════════════════════════════════════════════════════════════════

class TestBackupsEndpoints(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_list_backups(self, mock_db):
        mock_db.return_value = [{"id": 1, "label": "pre-update"}]
        resp = client.get("/api/backups")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("backups", data)

    @patch("dashboard.app.db.execute", side_effect=Exception("DB error"))
    def test_list_backups_error(self, mock_db):
        resp = client.get("/api/backups")
        data = resp.json()
        self.assertIn("error", data)


# ═══════════════════════════════════════════════════════════════════════
# Updates API
# ═══════════════════════════════════════════════════════════════════════

class TestUpdatesEndpoint(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_list_updates(self, mock_db):
        mock_db.return_value = []
        resp = client.get("/api/updates")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("updates", data)


# ═══════════════════════════════════════════════════════════════════════
# Config API
# ═══════════════════════════════════════════════════════════════════════

class TestConfigEndpoint(unittest.TestCase):

    def test_get_config(self):
        resp = client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("config", data)


# ═══════════════════════════════════════════════════════════════════════
# Audit API
# ═══════════════════════════════════════════════════════════════════════

class TestAuditEndpoints(unittest.TestCase):

    @patch("engines.auditor.audit_system")
    def test_audit_system(self, mock_audit):
        mock_audit.return_value = {"name": "MAME", "health_score": 90.0}
        resp = client.post("/api/audit/system/MAME")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["result"]["name"], "MAME")


# ═══════════════════════════════════════════════════════════════════════
# Plugin REST endpoints
# ═══════════════════════════════════════════════════════════════════════

class TestPluginEndpoints(unittest.TestCase):

    @patch("dashboard.app.plugin_manager")
    def test_plugin_list(self, mock_pm):
        mock_pm.list_plugins.return_value = [
            {"name": "example_plugin", "state": "enabled"},
        ]
        resp = client.get("/api/plugins")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("plugins", data)

    @patch("dashboard.app.plugin_manager")
    def test_plugin_discover(self, mock_pm):
        mock_pm.discover.return_value = ["example_plugin", "rom_cleaner"]
        resp = client.get("/api/plugins/discover")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("available", data)

    @patch("dashboard.app.plugin_manager")
    def test_plugin_enable(self, mock_pm):
        mock_pm.enable.return_value = True
        resp = client.post("/api/plugins/example_plugin/enable")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["enabled"])

    @patch("dashboard.app.plugin_manager")
    def test_plugin_disable(self, mock_pm):
        mock_pm.disable.return_value = True
        resp = client.post("/api/plugins/example_plugin/disable")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["disabled"])

    @patch("dashboard.app.plugin_manager")
    def test_plugin_unload(self, mock_pm):
        mock_pm.unload.return_value = True
        resp = client.post("/api/plugins/example_plugin/unload")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["unloaded"])

    @patch("dashboard.app.plugin_manager")
    def test_plugin_info_not_found(self, mock_pm):
        mock_pm.get_plugin.return_value = None
        resp = client.get("/api/plugins/nonexistent/info")
        self.assertEqual(resp.status_code, 404)

    @patch("dashboard.app.plugin_manager")
    def test_plugin_events(self, mock_pm):
        mock_pm.event_bus.list_events.return_value = ["plugin.enabled"]
        mock_pm.event_bus.listener_count.return_value = 2
        resp = client.get("/api/plugins/events")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("events", data)
        self.assertIn("total_events", data)

    @patch("dashboard.app.plugin_manager")
    def test_plugin_create_missing_name(self, mock_pm):
        resp = client.post("/api/plugins/create", json={"name": ""})
        self.assertEqual(resp.status_code, 400)

    @patch("dashboard.app.plugin_manager")
    def test_plugin_create_duplicate(self, mock_pm):
        mock_pm.create_plugin_scaffold.side_effect = FileExistsError("exists")
        resp = client.post("/api/plugins/create", json={"name": "dup"})
        self.assertEqual(resp.status_code, 409)


# ═══════════════════════════════════════════════════════════════════════
# AI API
# ═══════════════════════════════════════════════════════════════════════

class TestAIEndpoints(unittest.TestCase):

    @patch("engines.ai_engine.get_ai")
    def test_ai_status(self, mock_get_ai):
        mock_ai = MagicMock()
        mock_ai.detect_available.return_value = {"ollama": False, "lmstudio": True}
        mock_get_ai.return_value = mock_ai
        resp = client.get("/api/ai/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("providers", data)


# ═══════════════════════════════════════════════════════════════════════
# Response content type
# ═══════════════════════════════════════════════════════════════════════

class TestResponseHeaders(unittest.TestCase):

    @patch("dashboard.app.db.execute")
    def test_json_content_type(self, mock_db):
        mock_db.return_value = []
        resp = client.get("/api/systems")
        self.assertIn("application/json", resp.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
