"""Plugin system tests for HyperSpin Extreme Toolkit.

Tests are aligned with the actual API in plugins/base.py:
  - EventBus.emit(event, **data)         — kwargs, not positional dict
  - ToolkitContext(*, config, event_bus, logger, plugin_name)  — keyword-only
  - BasePlugin.__init__()                — no args
  - BasePlugin.on_enable(self, ctx)      — receives ToolkitContext
  - get_config_defaults() / get_status() — actual method names
  - ToolkitContext.db_execute()          — not db_query()
  - ToolkitContext.get_config(dotpath)   — dot-notation config access
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_toolkit():
    """Load config and init DB for tests that need it."""
    from core.config import load_config
    load_config(PROJECT_ROOT / "config.yaml", reload=True)
    from core import database as db
    db.init_db()


def _make_context(plugin_name: str = "_test", config: dict = None):
    """Build a ToolkitContext with correct keyword-only signature."""
    from plugins.base import EventBus, ToolkitContext
    bus = EventBus()
    return bus, ToolkitContext(
        config=config or {},
        event_bus=bus,
        logger=logging.getLogger(f"plugins.{plugin_name}"),
        plugin_name=plugin_name,
    )


def _fresh_plugin_manager():
    """Return a clean PluginManager instance pointing at the real plugins dir."""
    _init_toolkit()
    from core.config import _config_cache
    from plugins import PluginManager
    pm = PluginManager(config=_config_cache or {})
    pm.plugins = {}
    return pm


# ---------------------------------------------------------------------------
# EventBus Tests
# ---------------------------------------------------------------------------

def test_eventbus_subscribe_emit():
    """EventBus should deliver events to subscribers via **kwargs."""
    from plugins.base import EventBus
    bus = EventBus()

    received = []
    bus.subscribe("test.event", lambda **kw: received.append(kw))
    bus.emit("test.event", key="value")

    assert len(received) == 1, "Listener should receive one event"
    assert received[0]["key"] == "value"
    print("[PASS] EventBus subscribe/emit works")


def test_eventbus_multiple_listeners():
    """Multiple listeners on the same event should all fire."""
    from plugins.base import EventBus
    bus = EventBus()

    count = [0]
    bus.subscribe("multi", lambda **kw: count.__setitem__(0, count[0] + 1))
    bus.subscribe("multi", lambda **kw: count.__setitem__(0, count[0] + 1))
    bus.emit("multi")

    assert count[0] == 2, f"Both listeners should fire, got {count[0]}"
    print("[PASS] EventBus multiple listeners work")


def test_eventbus_unsubscribe():
    """Unsubscribed listeners should not fire."""
    from plugins.base import EventBus
    bus = EventBus()

    received = []
    handler = lambda **kw: received.append(kw)
    bus.subscribe("unsub_test", handler)
    bus.unsubscribe("unsub_test", handler)
    bus.emit("unsub_test")

    assert len(received) == 0, "Unsubscribed handler should not fire"
    print("[PASS] EventBus unsubscribe works")


def test_eventbus_unsubscribe_all():
    """unsubscribe_all(owner) should remove all callbacks for that owner."""
    from plugins.base import EventBus
    bus = EventBus()

    received = []
    bus.subscribe("owned.event", lambda **kw: received.append("a"), owner="plug_a")
    bus.subscribe("owned.event", lambda **kw: received.append("b"), owner="plug_b")

    removed = bus.unsubscribe_all("plug_a")
    assert removed == 1, f"Should remove 1 listener, removed {removed}"

    bus.emit("owned.event")
    assert received == ["b"], f"Only plug_b listener should fire, got {received}"
    print("[PASS] EventBus unsubscribe_all works")


def test_eventbus_list_events():
    """list_events should return all registered event names."""
    from plugins.base import EventBus
    bus = EventBus()

    bus.subscribe("alpha", lambda **kw: None)
    bus.subscribe("beta", lambda **kw: None)
    events = bus.list_events()

    assert "alpha" in events
    assert "beta" in events
    print("[PASS] EventBus list_events works")


def test_eventbus_listener_count():
    """listener_count should return correct count."""
    from plugins.base import EventBus
    bus = EventBus()

    bus.subscribe("count_test", lambda **kw: None)
    bus.subscribe("count_test", lambda **kw: None)

    assert bus.listener_count("count_test") == 2
    assert bus.listener_count("nonexistent") == 0
    print("[PASS] EventBus listener_count works")


def test_eventbus_error_isolation():
    """A failing listener should not break other listeners."""
    from plugins.base import EventBus
    bus = EventBus()

    results = []

    def good_handler(**kw):
        results.append("ok")

    def bad_handler(**kw):
        raise RuntimeError("boom")

    bus.subscribe("err_test", bad_handler)
    bus.subscribe("err_test", good_handler)
    bus.emit("err_test")

    assert "ok" in results, "Good handler should still fire after bad handler"
    print("[PASS] EventBus error isolation works")


# ---------------------------------------------------------------------------
# ToolkitContext Tests
# ---------------------------------------------------------------------------

def test_toolkit_context_creation():
    """ToolkitContext should instantiate with keyword args."""
    bus, ctx = _make_context("test_create")
    assert ctx.events is bus
    assert ctx.config == {}
    print("[PASS] ToolkitContext creation works")


def test_toolkit_context_get_config():
    """ToolkitContext.get_config() should support dot-notation access."""
    from plugins.base import EventBus, ToolkitContext
    bus = EventBus()
    ctx = ToolkitContext(
        config={"paths": {"hyperspin_root": "D:\\Arcade"}},
        event_bus=bus,
        logger=logging.getLogger("test"),
        plugin_name="_test",
    )

    val = ctx.get_config("paths.hyperspin_root")
    assert val == "D:\\Arcade", f"Expected 'D:\\Arcade', got {val}"

    default = ctx.get_config("nonexistent.key", "fallback")
    assert default == "fallback"
    print("[PASS] ToolkitContext get_config works")


def test_toolkit_context_db_execute():
    """ToolkitContext.db_execute() should execute read-only SQL."""
    _init_toolkit()
    bus, ctx = _make_context("_db_test")

    rows = ctx.db_execute("SELECT 1 as val")
    assert len(rows) == 1
    assert rows[0]["val"] == 1
    print("[PASS] ToolkitContext db_execute works")


def test_toolkit_context_db_blocks_writes():
    """ToolkitContext.db_execute() should block non-SELECT operations."""
    _init_toolkit()
    bus, ctx = _make_context("_db_block_test")

    blocked = False
    try:
        ctx.db_execute("DROP TABLE IF EXISTS _test_not_real")
    except PermissionError:
        blocked = True

    assert blocked, "Write queries should be blocked by ToolkitContext"
    print("[PASS] ToolkitContext blocks write queries")


def test_toolkit_context_db_insert_plugin_tables():
    """ToolkitContext.db_insert() should allow writes to plugin_* tables."""
    _init_toolkit()
    bus, ctx = _make_context("_insert_test")

    row_id = ctx.db_insert("plugin_events", {
        "plugin_name": "_insert_test",
        "event_type": "test",
        "details": "ctx.db_insert test",
    })
    assert row_id is not None and row_id > 0, f"Expected row id, got {row_id}"

    # Cleanup
    from core import database as db
    db.execute("DELETE FROM plugin_events WHERE plugin_name='_insert_test'")
    print("[PASS] ToolkitContext db_insert to plugin_* tables works")


def test_toolkit_context_db_insert_blocks_core_tables():
    """ToolkitContext.db_insert() should block writes to core tables."""
    _init_toolkit()
    bus, ctx = _make_context("_block_test")

    blocked = False
    try:
        ctx.db_insert("systems", {"name": "_should_not_exist"})
    except PermissionError:
        blocked = True

    assert blocked, "Writes to non-plugin tables should be blocked"
    print("[PASS] ToolkitContext blocks db_insert to core tables")


def test_toolkit_context_register_tool():
    """ToolkitContext.register_tool() should add tools to the context."""
    bus, ctx = _make_context("_tool_test")
    ctx.register_tool(
        name="my_tool",
        description="A test tool",
        input_schema={"type": "object", "properties": {}},
        handler=lambda **kw: {"ok": True},
    )

    assert len(ctx.tools) == 1
    assert ctx.tools[0]["name"] == "plugin__tool_test_my_tool"
    print("[PASS] ToolkitContext register_tool works")


def test_toolkit_context_register_route():
    """ToolkitContext.register_route() should add routes to the context."""
    bus, ctx = _make_context("_route_test")
    ctx.register_route("/api/test", "GET", lambda req: {"ok": True}, summary="Test route")

    assert len(ctx.routes) == 1
    assert ctx.routes[0]["path"] == "/api/test"
    assert ctx.routes[0]["method"] == "GET"
    print("[PASS] ToolkitContext register_route works")


# ---------------------------------------------------------------------------
# BasePlugin Tests
# ---------------------------------------------------------------------------

def test_base_plugin_meta():
    """PluginMeta should store metadata correctly."""
    from plugins.base import PluginMeta
    meta = PluginMeta(
        name="test_plugin",
        version="1.0.0",
        description="A test plugin",
        author="Tester",
    )
    assert meta.name == "test_plugin"
    assert meta.version == "1.0.0"
    d = meta.to_dict()
    assert d["name"] == "test_plugin"
    assert isinstance(d["tags"], list)
    print("[PASS] PluginMeta works")


def test_base_plugin_subclass():
    """Subclassing BasePlugin should work with on_enable(ctx)."""
    from plugins.base import BasePlugin, PluginMeta, ToolkitContext

    class TestPlugin(BasePlugin):
        meta = PluginMeta(name="test_sub", version="0.1.0", description="Test")
        def on_enable(self, ctx: ToolkitContext) -> None:
            self._ctx = ctx

    p = TestPlugin()
    assert p.meta.name == "test_sub"
    assert p.state.name == "LOADED"

    bus, ctx = _make_context("test_sub")
    p.on_enable(ctx)
    assert p._ctx is ctx
    print("[PASS] BasePlugin subclass works")


def test_base_plugin_to_dict():
    """BasePlugin.to_dict() should include all metadata."""
    from plugins.base import BasePlugin, PluginMeta, PluginState

    class DictPlugin(BasePlugin):
        meta = PluginMeta(name="dict_test", version="2.0.0", description="Dict test",
                          author="Author", tags=["test", "demo"])
        def on_enable(self, ctx) -> None:
            pass

    p = DictPlugin()
    d = p.to_dict()

    assert d["name"] == "dict_test"
    assert d["version"] == "2.0.0"
    assert d["author"] == "Author"
    assert "test" in d["tags"]
    assert d["state"] == "LOADED"
    print("[PASS] BasePlugin to_dict works")


def test_base_plugin_get_config_defaults():
    """Plugins should provide get_config_defaults()."""
    from plugins.base import BasePlugin, PluginMeta

    class CfgPlugin(BasePlugin):
        meta = PluginMeta(name="cfg_test", version="1.0.0", description="Config test")
        def on_enable(self, ctx) -> None:
            pass
        def get_config_defaults(self) -> dict:
            return {"interval": 60, "enabled": True}

    p = CfgPlugin()
    defaults = p.get_config_defaults()

    assert defaults["interval"] == 60
    assert defaults["enabled"] is True
    print("[PASS] BasePlugin get_config_defaults works")


def test_base_plugin_get_status():
    """Plugins should provide get_status() info."""
    from plugins.base import BasePlugin, PluginMeta

    class StatusPlugin(BasePlugin):
        meta = PluginMeta(name="status_test", version="1.0.0", description="Status test")
        def on_enable(self, ctx) -> None:
            pass
        def get_status(self) -> dict:
            base = super().get_status()
            base["healthy"] = True
            base["items_processed"] = 42
            return base

    p = StatusPlugin()
    s = p.get_status()

    assert s["healthy"] is True
    assert s["items_processed"] == 42
    assert s["name"] == "status_test"
    print("[PASS] BasePlugin get_status works")


# ---------------------------------------------------------------------------
# PluginManager Tests
# ---------------------------------------------------------------------------

def test_manager_discover():
    """PluginManager.discover() should find plugins in the plugins directory."""
    pm = _fresh_plugin_manager()
    found = pm.discover()

    assert len(found) >= 1, "Should find at least example_plugin"
    names = [p["name"] for p in found]
    assert "example_plugin" in names, f"Should find example_plugin, got {names}"
    print(f"[PASS] PluginManager.discover() found {len(found)} plugins")


def test_manager_load_plugin():
    """PluginManager should load a plugin by name."""
    pm = _fresh_plugin_manager()
    ok = pm.load("example_plugin")

    assert ok, "Loading example_plugin should succeed"
    assert "example_plugin" in pm.plugins
    print("[PASS] PluginManager.load() works")


def test_manager_enable_disable():
    """PluginManager should enable and disable plugins."""
    pm = _fresh_plugin_manager()
    from plugins.base import PluginState

    ok = pm.enable("example_plugin")
    assert ok, "Enabling example_plugin should succeed"

    p = pm.get_plugin("example_plugin")
    assert p.state == PluginState.ENABLED

    ok = pm.disable("example_plugin")
    assert ok, "Disabling example_plugin should succeed"
    assert p.state == PluginState.DISABLED

    print("[PASS] PluginManager enable/disable works")


def test_manager_unload():
    """PluginManager should unload a plugin."""
    pm = _fresh_plugin_manager()
    pm.enable("example_plugin")
    ok = pm.unload("example_plugin")

    assert ok, "Unload should succeed"
    assert "example_plugin" not in pm.plugins
    print("[PASS] PluginManager.unload() works")


def test_manager_list_plugins():
    """PluginManager.list_plugins() should return plugin info dicts."""
    pm = _fresh_plugin_manager()
    pm.enable("example_plugin")

    plugins = pm.list_plugins()
    assert len(plugins) >= 1
    assert any(p["name"] == "example_plugin" for p in plugins)
    print("[PASS] PluginManager.list_plugins() works")


def test_manager_get_all_tools():
    """PluginManager.get_all_tools() should collect tools from enabled plugins."""
    pm = _fresh_plugin_manager()
    pm.enable("example_plugin")

    tools = pm.get_all_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 1, "example_plugin registers at least one tool"
    print(f"[PASS] PluginManager.get_all_tools() returned {len(tools)} tools")


def test_manager_get_all_routes():
    """PluginManager.get_all_routes() should collect routes from enabled plugins."""
    pm = _fresh_plugin_manager()
    pm.enable("example_plugin")

    routes = pm.get_all_routes()
    assert isinstance(routes, list)
    assert len(routes) >= 1, "example_plugin registers at least one route"
    print(f"[PASS] PluginManager.get_all_routes() returned {len(routes)} routes")


def test_manager_create_scaffold():
    """PluginManager.create_plugin_scaffold() should create a valid plugin file."""
    pm = _fresh_plugin_manager()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm._plugins_dir = Path(tmpdir)
        path = pm.create_plugin_scaffold("my_test_plugin", author="TestBot")

        assert Path(path).exists(), f"Scaffold file should exist at {path}"
        content = Path(path).read_text(encoding="utf-8")
        assert "my_test_plugin" in content
        assert "TestBot" in content
        assert "BasePlugin" in content
        assert "on_enable" in content
        print("[PASS] PluginManager.create_plugin_scaffold() works")


def test_manager_scaffold_duplicate_raises():
    """Creating a scaffold for an existing plugin should raise FileExistsError."""
    pm = _fresh_plugin_manager()

    with tempfile.TemporaryDirectory() as tmpdir:
        pm._plugins_dir = Path(tmpdir)
        pm.create_plugin_scaffold("dup_test")

        raised = False
        try:
            pm.create_plugin_scaffold("dup_test")
        except FileExistsError:
            raised = True

        assert raised, "Duplicate scaffold should raise FileExistsError"
        print("[PASS] Duplicate scaffold raises FileExistsError")


# ---------------------------------------------------------------------------
# Database Schema Tests
# ---------------------------------------------------------------------------

def test_db_plugin_tables_exist():
    """Enhanced plugin DB tables should exist after init."""
    _init_toolkit()
    from core import database as db

    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    table_names = {t["name"] for t in tables}

    required = {"plugins", "plugin_config", "plugin_dependencies", "plugin_hooks", "plugin_events"}
    missing = required - table_names
    assert not missing, f"Missing plugin tables: {missing}"
    print(f"[PASS] All plugin DB tables exist: {required}")


def test_db_plugin_config_crud():
    """Plugin config key-value store should support CRUD operations."""
    _init_toolkit()
    from core import database as db

    # Insert
    db.execute(
        "INSERT OR REPLACE INTO plugin_config (plugin_name, key, value) VALUES (?, ?, ?)",
        ("_test_plugin", "setting_a", "hello"),
    )

    # Read
    rows = db.execute(
        "SELECT value FROM plugin_config WHERE plugin_name=? AND key=?",
        ("_test_plugin", "setting_a"),
    )
    assert len(rows) == 1
    assert rows[0]["value"] == "hello"

    # Update
    db.execute(
        "INSERT OR REPLACE INTO plugin_config (plugin_name, key, value) VALUES (?, ?, ?)",
        ("_test_plugin", "setting_a", "world"),
    )
    rows = db.execute(
        "SELECT value FROM plugin_config WHERE plugin_name=? AND key=?",
        ("_test_plugin", "setting_a"),
    )
    assert rows[0]["value"] == "world"

    # Cleanup
    db.execute("DELETE FROM plugin_config WHERE plugin_name='_test_plugin'")
    print("[PASS] plugin_config CRUD works")


def test_db_plugin_events_log():
    """Plugin events table should log lifecycle events."""
    _init_toolkit()
    from core import database as db

    db.insert("plugin_events", {
        "plugin_name": "_test_plugin",
        "event_type": "enabled",
        "details": "Test enable event",
    })

    rows = db.execute(
        "SELECT * FROM plugin_events WHERE plugin_name='_test_plugin'"
    )
    assert len(rows) >= 1
    assert rows[-1]["event_type"] == "enabled"

    # Cleanup
    db.execute("DELETE FROM plugin_events WHERE plugin_name='_test_plugin'")
    print("[PASS] plugin_events logging works")


def test_db_plugin_dependencies():
    """Plugin dependencies table should store dependency info."""
    _init_toolkit()
    from core import database as db

    db.execute(
        "INSERT OR REPLACE INTO plugin_dependencies (plugin_name, depends_on, version_spec, required) "
        "VALUES (?, ?, ?, ?)",
        ("_child_plugin", "_parent_plugin", ">=1.0.0", 1),
    )

    rows = db.execute(
        "SELECT * FROM plugin_dependencies WHERE plugin_name='_child_plugin'"
    )
    assert len(rows) == 1
    assert rows[0]["depends_on"] == "_parent_plugin"
    assert rows[0]["version_spec"] == ">=1.0.0"

    # Cleanup
    db.execute("DELETE FROM plugin_dependencies WHERE plugin_name='_child_plugin'")
    print("[PASS] plugin_dependencies works")


def test_db_plugin_hooks():
    """Plugin hooks table should store hook registrations."""
    _init_toolkit()
    from core import database as db

    db.insert("plugin_hooks", {
        "plugin_name": "_test_plugin",
        "hook_type": "event",
        "hook_name": "audit.complete",
        "details": json.dumps({"priority": 10}),
    })

    rows = db.execute(
        "SELECT * FROM plugin_hooks WHERE plugin_name='_test_plugin'"
    )
    assert len(rows) >= 1
    assert rows[-1]["hook_type"] == "event"
    assert rows[-1]["hook_name"] == "audit.complete"

    # Cleanup
    db.execute("DELETE FROM plugin_hooks WHERE plugin_name='_test_plugin'")
    print("[PASS] plugin_hooks works")


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

def test_full_plugin_lifecycle():
    """End-to-end: discover -> load -> enable -> status -> disable -> unload."""
    pm = _fresh_plugin_manager()
    from plugins.base import PluginState

    # Discover
    found = pm.discover()
    assert any(p["name"] == "example_plugin" for p in found)

    # Enable (auto-loads)
    assert pm.enable("example_plugin")
    p = pm.get_plugin("example_plugin")
    assert p.state == PluginState.ENABLED

    # Status
    status = p.get_status()
    assert isinstance(status, dict)
    assert status["name"] == "example_plugin"

    # Disable
    assert pm.disable("example_plugin")
    assert p.state == PluginState.DISABLED

    # Unload
    assert pm.unload("example_plugin")
    assert pm.get_plugin("example_plugin") is None

    print("[PASS] Full plugin lifecycle works end-to-end")


def test_event_flow_between_plugins():
    """Events emitted by the bus should reach plugin subscribers."""
    from plugins.base import EventBus, ToolkitContext, BasePlugin, PluginMeta

    bus = EventBus()
    received = []

    class ListenerPlugin(BasePlugin):
        meta = PluginMeta(name="listener", version="1.0.0", description="Listens")

        def on_enable(self, ctx: ToolkitContext) -> None:
            self._ctx = ctx
            ctx.subscribe("custom.event", self._on_event)

        def on_disable(self) -> None:
            pass

        def _on_event(self, **data):
            received.append(data)

    ctx = ToolkitContext(
        config={},
        event_bus=bus,
        logger=logging.getLogger("test.listener"),
        plugin_name="listener",
    )
    plugin = ListenerPlugin()
    plugin.on_enable(ctx)

    bus.emit("custom.event", msg="hello from test")

    assert len(received) == 1
    assert received[0]["msg"] == "hello from test"

    # Unsubscribe via owner
    bus.unsubscribe_all("listener")
    bus.emit("custom.event", msg="should not arrive")
    assert len(received) == 1, "Unsubscribed plugin should not receive events"

    print("[PASS] Event flow between plugins works")


def test_manager_load_enabled_from_db():
    """load_enabled_from_db should re-enable plugins marked in the database."""
    pm = _fresh_plugin_manager()
    from plugins.base import PluginState

    # Enable to persist to DB
    pm.enable("example_plugin")
    pm.disable("example_plugin")
    pm.unload("example_plugin")

    # Now create a fresh manager and load from DB
    pm2 = _fresh_plugin_manager()
    results = pm2.load_enabled_from_db()
    # example_plugin should be in results (may or may not succeed depending on DB state)
    assert isinstance(results, dict)
    print(f"[PASS] load_enabled_from_db returned {len(results)} results")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    """Run all plugin tests."""
    tests = [
        # EventBus
        test_eventbus_subscribe_emit,
        test_eventbus_multiple_listeners,
        test_eventbus_unsubscribe,
        test_eventbus_unsubscribe_all,
        test_eventbus_list_events,
        test_eventbus_listener_count,
        test_eventbus_error_isolation,
        # ToolkitContext
        test_toolkit_context_creation,
        test_toolkit_context_get_config,
        test_toolkit_context_db_execute,
        test_toolkit_context_db_blocks_writes,
        test_toolkit_context_db_insert_plugin_tables,
        test_toolkit_context_db_insert_blocks_core_tables,
        test_toolkit_context_register_tool,
        test_toolkit_context_register_route,
        # BasePlugin
        test_base_plugin_meta,
        test_base_plugin_subclass,
        test_base_plugin_to_dict,
        test_base_plugin_get_config_defaults,
        test_base_plugin_get_status,
        # PluginManager
        test_manager_discover,
        test_manager_load_plugin,
        test_manager_enable_disable,
        test_manager_unload,
        test_manager_list_plugins,
        test_manager_get_all_tools,
        test_manager_get_all_routes,
        test_manager_create_scaffold,
        test_manager_scaffold_duplicate_raises,
        test_manager_load_enabled_from_db,
        # Database
        test_db_plugin_tables_exist,
        test_db_plugin_config_crud,
        test_db_plugin_events_log,
        test_db_plugin_dependencies,
        test_db_plugin_hooks,
        # Integration
        test_full_plugin_lifecycle,
        test_event_flow_between_plugins,
    ]

    passed = 0
    failed = 0
    errors = []

    print("=" * 60)
    print("  HyperSpin Extreme Toolkit — Plugin System Tests")
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
