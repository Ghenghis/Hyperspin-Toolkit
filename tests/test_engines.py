"""Engine test suite — auditor, space_optimizer, ai_engine, drive_manager, cli_anything_bridge.

Uses mocks for filesystem/network calls so tests run fast and without
side effects on the real arcade collection.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure config is loaded before any engine import
from core.config import load_config
load_config(PROJECT_ROOT / "config.yaml", reload=True)


# ═══════════════════════════════════════════════════════════════════════
# Space Optimizer
# ═══════════════════════════════════════════════════════════════════════

class TestSpaceOptimizerHelpers(unittest.TestCase):
    """Unit tests for space_optimizer utility functions."""

    def test_human_size_bytes(self):
        from engines.space_optimizer import _human_size
        self.assertIn("B", _human_size(512))

    def test_human_size_kb(self):
        from engines.space_optimizer import _human_size
        result = _human_size(2048)
        self.assertIn("KB", result)

    def test_human_size_mb(self):
        from engines.space_optimizer import _human_size
        result = _human_size(5 * 1024 * 1024)
        self.assertIn("MB", result)

    def test_human_size_gb(self):
        from engines.space_optimizer import _human_size
        result = _human_size(3 * 1024 * 1024 * 1024)
        self.assertIn("GB", result)

    def test_human_size_tb(self):
        from engines.space_optimizer import _human_size
        result = _human_size(2 * 1024 * 1024 * 1024 * 1024)
        self.assertIn("TB", result)

    def test_hash_file_real(self):
        from engines.space_optimizer import _hash_file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"test content for hashing")
            f.flush()
            fpath = Path(f.name)
        try:
            h = _hash_file(fpath)
            self.assertTrue(len(h) > 0, "Hash should be non-empty")
            expected = hashlib.md5(b"test content for hashing").hexdigest()
            self.assertEqual(h, expected)
        finally:
            fpath.unlink(missing_ok=True)

    def test_hash_file_nonexistent(self):
        from engines.space_optimizer import _hash_file
        h = _hash_file(Path("Z:\\nonexistent\\file.bin"))
        self.assertEqual(h, "")


class TestSpaceOptimizerDuplicates(unittest.TestCase):
    """Test duplicate ROM detection with temp files."""

    def test_find_duplicates_in_temp_dir(self):
        from engines.space_optimizer import find_duplicate_roms
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two identical files
            content = b"A" * 2048
            (Path(tmpdir) / "game1.zip").write_bytes(content)
            (Path(tmpdir) / "game2.zip").write_bytes(content)
            # Create one unique file
            (Path(tmpdir) / "unique.zip").write_bytes(b"B" * 2048)

            result = find_duplicate_roms(
                rom_dirs=[tmpdir],
                min_size=1024,
                extensions={".zip"},
            )

            self.assertIn("duplicates", result)
            self.assertIn("total_wasted", result)
            self.assertIn("file_count", result)
            self.assertEqual(result["file_count"], 3)
            self.assertEqual(result["duplicate_groups"], 1)
            self.assertEqual(result["duplicates"][0]["count"], 2)

    def test_find_duplicates_empty_dir(self):
        from engines.space_optimizer import find_duplicate_roms
        with tempfile.TemporaryDirectory() as tmpdir:
            result = find_duplicate_roms(rom_dirs=[tmpdir])
            self.assertEqual(result["duplicate_groups"], 0)
            self.assertEqual(result["file_count"], 0)

    def test_find_duplicates_nonexistent_dir(self):
        from engines.space_optimizer import find_duplicate_roms
        result = find_duplicate_roms(rom_dirs=["Z:\\nonexistent"])
        self.assertEqual(result["file_count"], 0)


class TestSpaceOptimizerRedundant(unittest.TestCase):
    """Test redundant emulator detection."""

    @patch("engines.space_optimizer.get")
    def test_find_redundant_nonexistent_root(self, mock_get):
        from engines.space_optimizer import find_redundant_emulators
        mock_get.return_value = "Z:\\nonexistent\\emulators"
        result = find_redundant_emulators()
        self.assertEqual(result["groups"], [])
        self.assertEqual(result["total_dirs"], 0)


# ═══════════════════════════════════════════════════════════════════════
# Drive Manager
# ═══════════════════════════════════════════════════════════════════════

class TestDriveManager(unittest.TestCase):
    """Test drive state persistence and detection logic."""

    def test_load_default_state(self):
        from engines.drive_manager import DEFAULT_STATE
        self.assertIn("primary", DEFAULT_STATE)
        self.assertIn("secondary", DEFAULT_STATE)
        self.assertIn("tertiary", DEFAULT_STATE)
        self.assertIsNone(DEFAULT_STATE["primary"])

    def test_save_and_load_state(self):
        from engines.drive_manager import save_state, load_state, DRIVES_STATE
        # Backup existing state
        backup = None
        if DRIVES_STATE.exists():
            backup = DRIVES_STATE.read_text(encoding="utf-8")

        try:
            test_state = {
                "primary": "D",
                "secondary": "E",
                "tertiary": None,
                "arcade_root": "Arcade",
                "secondary_root": "Arcade",
                "tertiary_root": "Arcade",
                "last_scan": "2026-03-17",
            }
            save_state(test_state)
            loaded = load_state()
            self.assertEqual(loaded["primary"], "D")
            self.assertEqual(loaded["secondary"], "E")
            self.assertEqual(loaded["last_scan"], "2026-03-17")
        finally:
            # Restore original state
            if backup is not None:
                DRIVES_STATE.write_text(backup, encoding="utf-8")
            elif DRIVES_STATE.exists():
                DRIVES_STATE.unlink()

    def test_get_all_drives_returns_list(self):
        from engines.drive_manager import _get_all_drives
        drives = _get_all_drives()
        self.assertIsInstance(drives, list)
        # On Windows, should find at least C:
        if sys.platform == "win32":
            self.assertIn("C", drives)

    def test_drive_usage_returns_dict(self):
        from engines.drive_manager import _drive_usage
        if sys.platform == "win32":
            usage = _drive_usage("C")
            self.assertIn("total_gb", usage)
            self.assertIn("free_gb", usage)
            self.assertIn("used_pct", usage)


# ═══════════════════════════════════════════════════════════════════════
# AI Engine
# ═══════════════════════════════════════════════════════════════════════

class TestAIEngineProviders(unittest.TestCase):
    """Test AI engine provider classes without requiring live LLM."""

    def test_llm_provider_base(self):
        from engines.ai_engine import LLMProvider
        p = LLMProvider("test", "http://localhost:9999", "test-model")
        self.assertEqual(p.name, "test")
        self.assertEqual(p.default_model, "test-model")
        self.assertEqual(p.timeout, 120)

    def test_llm_provider_not_available_when_offline(self):
        from engines.ai_engine import LLMProvider
        p = LLMProvider("test", "http://127.0.0.1:59999", "test-model")
        self.assertFalse(p.is_available())

    def test_ollama_provider_init(self):
        from engines.ai_engine import OllamaProvider
        p = OllamaProvider()
        self.assertEqual(p.name, "ollama")
        self.assertIn("localhost", p.base_url)

    def test_ollama_list_models_offline(self):
        from engines.ai_engine import OllamaProvider
        p = OllamaProvider()
        # Should return empty list when Ollama is not running
        models = p.list_models()
        self.assertIsInstance(models, list)

    def test_base_chat_raises(self):
        from engines.ai_engine import LLMProvider
        p = LLMProvider("test", "http://localhost:9999", "model")
        with self.assertRaises(NotImplementedError):
            p.chat([{"role": "user", "content": "hello"}])

    def test_base_generate_raises(self):
        from engines.ai_engine import LLMProvider
        p = LLMProvider("test", "http://localhost:9999", "model")
        with self.assertRaises(NotImplementedError):
            p.generate("hello")


# ═══════════════════════════════════════════════════════════════════════
# CLI-Anything Bridge
# ═══════════════════════════════════════════════════════════════════════

class TestCLIAnythingBridge(unittest.TestCase):
    """Test static command mapping and entity extraction."""

    def test_extract_entities_system(self):
        from engines.cli_anything_bridge import _extract_entities
        entities = _extract_entities("audit the MAME system")
        self.assertEqual(entities.get("system"), "MAME")

    def test_extract_entities_path(self):
        from engines.cli_anything_bridge import _extract_entities
        entities = _extract_entities("backup D:\\Arcade\\ROMs")
        self.assertEqual(entities.get("path"), "D:\\Arcade\\ROMs")

    def test_extract_entities_backup_id(self):
        from engines.cli_anything_bridge import _extract_entities
        entities = _extract_entities("rollback to bk_20260315")
        self.assertEqual(entities.get("id"), "bk_20260315")

    def test_extract_entities_auto_label(self):
        from engines.cli_anything_bridge import _extract_entities
        entities = _extract_entities("backup my collection")
        self.assertIn("label", entities)
        self.assertTrue(entities["label"].startswith("auto-"))

    def test_extract_entities_known_path(self):
        from engines.cli_anything_bridge import _extract_entities
        entities = _extract_entities("scan roms directory")
        self.assertIn("path", entities)

    def test_static_map_lookup(self):
        from engines.cli_anything_bridge import resolve_command
        result = resolve_command("full audit")
        self.assertIsInstance(result, dict)
        self.assertIn("command", result)
        self.assertIn("audit full", result["command"])
        self.assertEqual(result["method"], "static")

    def test_static_map_stats(self):
        from engines.cli_anything_bridge import resolve_command
        result = resolve_command("collection stats")
        self.assertIsInstance(result, dict)
        self.assertIn("stats", result["command"])

    def test_static_map_unknown_returns_dict(self):
        from engines.cli_anything_bridge import resolve_command
        # Unknown command falls through to LLM fallback (returns dict)
        result = resolve_command("xyzzy random gibberish 12345")
        self.assertIsInstance(result, dict)
        self.assertIn("command", result)


# ═══════════════════════════════════════════════════════════════════════
# Auditor
# ═══════════════════════════════════════════════════════════════════════

class TestAuditorHealthScore(unittest.TestCase):
    """Test health score calculation logic."""

    def test_calculate_health_score_empty(self):
        from engines.auditor import _calculate_health_score
        result = _calculate_health_score({
            "summary": {
                "total_systems": 0,
                "systems_with_roms": 0,
                "systems_with_xml": 0,
                "total_emulators": 0,
                "healthy_emulators": 0,
            },
            "rocketlauncher": {"exists": False, "exe_exists": False},
            "systems": {},
        })
        self.assertEqual(result, 0.0)

    def test_calculate_health_score_perfect(self):
        from engines.auditor import _calculate_health_score
        result = _calculate_health_score({
            "summary": {
                "total_systems": 10,
                "systems_with_roms": 10,
                "systems_with_xml": 10,
                "total_emulators": 5,
                "healthy_emulators": 5,
            },
            "rocketlauncher": {"exists": True, "exe_exists": True},
            "systems": {
                f"sys_{i}": {"health_score": 100} for i in range(10)
            },
        })
        self.assertEqual(result, 100.0)

    def test_calculate_health_score_partial(self):
        from engines.auditor import _calculate_health_score
        result = _calculate_health_score({
            "summary": {
                "total_systems": 10,
                "systems_with_roms": 5,
                "systems_with_xml": 5,
                "total_emulators": 10,
                "healthy_emulators": 5,
            },
            "rocketlauncher": {"exists": True, "exe_exists": True},
            "systems": {
                f"sys_{i}": {"health_score": 50} for i in range(10)
            },
        })
        self.assertGreater(result, 0)
        self.assertLess(result, 100)


class TestAuditorEmulators(unittest.TestCase):
    """Test emulator audit with real filesystem."""

    def test_audit_emulators_returns_list(self):
        from engines.auditor import audit_emulators
        result = audit_emulators()
        self.assertIsInstance(result, list)
        # Should find emulators on the actual arcade drive
        if result:
            emu = result[0]
            self.assertIn("name", emu)
            self.assertIn("exe_count", emu)
            self.assertIn("is_healthy", emu)
            self.assertIn("total_size_mb", emu)


class TestAuditorRocketLauncher(unittest.TestCase):
    """Test RocketLauncher audit."""

    def test_audit_rocketlauncher_returns_dict(self):
        from engines.auditor import audit_rocketlauncher
        result = audit_rocketlauncher()
        self.assertIsInstance(result, dict)
        self.assertIn("path", result)
        self.assertIn("exists", result)
        self.assertIn("issues", result)


# ═══════════════════════════════════════════════════════════════════════
# NemoClaw Agents
# ═══════════════════════════════════════════════════════════════════════

class TestNemoClawAgents(unittest.TestCase):
    """Test NemoClaw agent configuration and data structures."""

    def test_agent_models_defined(self):
        from engines.nemoclaw_agents import AGENT_MODELS, AGENT_MODELS_OLLAMA
        self.assertIn("RomSpecialist", AGENT_MODELS)
        self.assertIn("EmulatorSpecialist", AGENT_MODELS)
        self.assertIn("MediaSpecialist", AGENT_MODELS)
        self.assertIn("DatabaseSpecialist", AGENT_MODELS)
        self.assertIn("SpaceOptimizer", AGENT_MODELS)
        self.assertIn("UpdateOrchestrator", AGENT_MODELS)
        # Ollama fallbacks
        for key in AGENT_MODELS:
            self.assertIn(key, AGENT_MODELS_OLLAMA)

    def test_agent_context_sizes(self):
        from engines.nemoclaw_agents import AGENT_CONTEXT
        self.assertIn("RomSpecialist", AGENT_CONTEXT)
        for role, ctx_len in AGENT_CONTEXT.items():
            self.assertGreater(ctx_len, 0, f"{role} context must be > 0")

    def test_lmstudio_url_configured(self):
        from engines.nemoclaw_agents import LMSTUDIO_URL, OLLAMA_URL
        self.assertIn("localhost", LMSTUDIO_URL)
        self.assertIn("localhost", OLLAMA_URL)


# ═══════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)
