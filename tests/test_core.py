"""Core module tests for HyperSpin Extreme Toolkit."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_config_loads():
    """Verify config.yaml loads and returns a dict."""
    from core.config import load_config
    cfg = load_config(PROJECT_ROOT / "config.yaml", reload=True)
    assert isinstance(cfg, dict), "Config should be a dict"
    assert "paths" in cfg, "Config must have 'paths' section"
    assert "ai" in cfg, "Config must have 'ai' section"
    assert "database" in cfg, "Config must have 'database' section"
    print("[PASS] config loads correctly")


def test_config_dot_access():
    """Verify dot-notation config access works."""
    from core.config import load_config, get
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    hs_root = get("paths.hyperspin_root")
    assert hs_root is not None, "paths.hyperspin_root should exist"
    assert "Arcade" in hs_root, "Should point to Arcade directory"
    print("[PASS] dot-notation config access works")


def test_database_init():
    """Verify database initializes and tables are created."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from core import database as db

    db.init_db()

    # Verify tables exist
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = {t["name"] for t in tables}
    required = {"systems", "roms", "emulators", "media_assets", "backups",
                "update_history", "audit_events", "ai_memory", "plugins", "schema_version"}
    missing = required - table_names
    assert not missing, f"Missing tables: {missing}"
    print(f"[PASS] database initialized with {len(table_names)} tables")


def test_database_crud():
    """Verify basic insert/query operations."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from core import database as db
    db.init_db()

    # Insert
    row_id = db.insert("audit_events", {
        "action": "test_event",
        "target": "test_target",
        "details": "test details",
        "severity": "INFO",
    })
    assert row_id > 0, "Insert should return a positive row ID"

    # Query
    rows = db.execute("SELECT * FROM audit_events WHERE action='test_event'")
    assert len(rows) >= 1, "Should find at least one test event"
    assert rows[-1]["target"] == "test_target"

    # Cleanup
    db.execute("DELETE FROM audit_events WHERE action='test_event'")
    print("[PASS] database CRUD operations work")


def test_logger():
    """Verify logger creates and writes."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from core.logger import get_logger

    log = get_logger("test")
    log.info("Test log message")
    log.warning("Test warning")
    print("[PASS] logger works")


def test_scanner_discover_systems():
    """Verify system discovery finds systems."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from engines.scanner import discover_systems

    systems = discover_systems()
    assert len(systems) > 0, "Should discover at least one system"
    assert any("Nintendo" in s["name"] for s in systems), "Should find Nintendo systems"
    print(f"[PASS] discovered {len(systems)} systems")


def test_scanner_discover_emulators():
    """Verify emulator discovery finds emulators."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from engines.scanner import discover_emulators

    emulators = discover_emulators()
    assert len(emulators) > 0, "Should discover at least one emulator"
    assert any("MAME" in e["name"] for e in emulators), "Should find MAME"
    print(f"[PASS] discovered {len(emulators)} emulators")


def test_backup_manifest():
    """Verify manifest building works on a small directory."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from engines.backup import build_manifest

    # Test on the toolkit's own core directory
    manifest = build_manifest(PROJECT_ROOT / "core")
    assert len(manifest) > 0, "Manifest should have entries"
    for rel_path, info in manifest.items():
        assert "hash" in info, f"Entry {rel_path} should have hash"
        assert "size" in info, f"Entry {rel_path} should have size"
    print(f"[PASS] built manifest with {len(manifest)} entries")


def test_backup_diff():
    """Verify manifest diff logic."""
    from engines.backup import diff_manifests

    old = {"a.txt": {"hash": "aaa", "size": 10}, "b.txt": {"hash": "bbb", "size": 20}}
    new = {"a.txt": {"hash": "aaa", "size": 10}, "b.txt": {"hash": "ccc", "size": 25}, "c.txt": {"hash": "ddd", "size": 30}}

    diff = diff_manifests(old, new)
    assert "c.txt" in diff["added"], "c.txt should be added"
    assert "b.txt" in diff["modified"], "b.txt should be modified"
    assert len(diff["deleted"]) == 0, "Nothing should be deleted"
    assert "a.txt" in diff["unchanged"], "a.txt should be unchanged"
    print("[PASS] manifest diff works correctly")


def test_plugin_discovery():
    """Verify plugin discovery finds the example plugin."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from plugins import discover_plugins

    plugins = discover_plugins()
    assert len(plugins) >= 1, "Should find at least the example plugin"
    names = [p["name"] for p in plugins]
    assert "example_plugin" in names, f"Should find example_plugin, got {names}"
    print(f"[PASS] discovered {len(plugins)} plugins")


def run_all():
    """Run all tests."""
    tests = [
        test_config_loads,
        test_config_dot_access,
        test_database_init,
        test_database_crud,
        test_logger,
        test_scanner_discover_systems,
        test_scanner_discover_emulators,
        test_backup_manifest,
        test_backup_diff,
        test_plugin_discovery,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("  HyperSpin Extreme Toolkit — Test Suite")
    print("=" * 60)
    print()

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            failed += 1
            errors.append((test_fn.__name__, str(exc)))
            print(f"[FAIL] {test_fn.__name__}: {exc}")

    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
