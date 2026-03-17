"""HyperSpin Extreme Toolkit — Plugin System.

Supports two plugin styles:

**Class-based (recommended)** — subclass ``BasePlugin``::

    from plugins.base import BasePlugin, PluginMeta, ToolkitContext

    class MyPlugin(BasePlugin):
        meta = PluginMeta(name="my_plugin", version="1.0.0",
                          description="Example plugin")
        def on_enable(self, ctx: ToolkitContext) -> None:
            ctx.log.info("Enabled!")

**Legacy module-level** (backwards-compatible)::

    PLUGIN_NAME = "my_legacy_plugin"
    PLUGIN_VERSION = "1.0.0"
    PLUGIN_DESCRIPTION = "Legacy-style plugin"
    def register(toolkit): ...
    def unregister(): ...

Public API:
    manager            — singleton PluginManager instance
    discover_plugins() — list available plugins (dict list)
    load_plugin(name)  — load a plugin by filename stem
    unload_plugin(name)— unload a loaded plugin
    get_loaded()       — dict of loaded plugin objects
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Any, Optional

from core.logger import get_logger, audit
from core import database as db

from plugins.base import (
    BasePlugin,
    EventBus,
    PluginMeta,
    PluginState,
    ToolkitContext,
)

log = get_logger("plugins")

# ---------------------------------------------------------------------------
# Legacy wrapper — wraps old-style modules to look like BasePlugin
# ---------------------------------------------------------------------------

class _LegacyPluginWrapper(BasePlugin):
    """Adapter wrapping a legacy module-level plugin as a BasePlugin."""

    def __init__(self, mod: Any, file_path: str) -> None:
        self.meta = PluginMeta(
            name=getattr(mod, "PLUGIN_NAME", Path(file_path).stem),
            version=getattr(mod, "PLUGIN_VERSION", "0.0.0"),
            description=getattr(mod, "PLUGIN_DESCRIPTION", ""),
        )
        super().__init__()
        self._mod = mod
        self._file = file_path

    def on_enable(self, ctx: ToolkitContext) -> None:
        self._ctx = ctx
        if hasattr(self._mod, "register"):
            self._mod.register(ctx)

    def on_disable(self) -> None:
        if hasattr(self._mod, "unregister"):
            self._mod.unregister()

    def on_unload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Plugin Manager
# ---------------------------------------------------------------------------

class PluginManager:
    """Central manager for plugin discovery, lifecycle, and integration.

    Attributes:
        event_bus: Shared EventBus instance used across all plugins.
        plugins:   Dict mapping plugin name → BasePlugin instance.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        self.event_bus = EventBus()
        self.plugins: dict[str, BasePlugin] = {}
        self._config = config or {}
        self._plugins_dir = Path(__file__).parent

    # -- Configuration ------------------------------------------------------

    def set_config(self, config: dict) -> None:
        """Update the toolkit config (called during toolkit init)."""
        self._config = config

    # -- Discovery ----------------------------------------------------------

    def discover(self) -> list[dict]:
        """Scan the plugins directory for all valid plugins.

        Detects both class-based (BasePlugin subclass) and legacy
        (module-level PLUGIN_NAME) plugins. Does **not** load them.

        Returns:
            List of dicts with keys: name, version, description, file,
            style ('class' or 'legacy').
        """
        found: list[dict] = []

        for py_file in sorted(self._plugins_dir.glob("*.py")):
            if py_file.name.startswith("_") or py_file.stem == "base":
                continue
            try:
                info = self._inspect_plugin_file(py_file)
                if info:
                    found.append(info)
            except Exception as exc:
                log.warning("Discovery failed for %s: %s", py_file.name, exc)

        return found

    def _inspect_plugin_file(self, py_file: Path) -> Optional[dict]:
        """Import a plugin module temporarily to extract metadata."""
        mod_name = f"_plugin_inspect_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(mod_name, str(py_file))
        if not spec or not spec.loader:
            return None

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # Check for class-based plugin (BasePlugin subclass)
        plugin_cls = self._find_plugin_class(mod)
        if plugin_cls is not None:
            meta = plugin_cls.meta
            return {
                "name": meta.name,
                "version": meta.version,
                "description": meta.description,
                "author": meta.author,
                "file": str(py_file),
                "style": "class",
                "tags": meta.tags,
                "dependencies": meta.dependencies,
            }

        # Check for legacy-style plugin
        if hasattr(mod, "PLUGIN_NAME") or hasattr(mod, "register"):
            return {
                "name": getattr(mod, "PLUGIN_NAME", py_file.stem),
                "version": getattr(mod, "PLUGIN_VERSION", "0.0.0"),
                "description": getattr(mod, "PLUGIN_DESCRIPTION", ""),
                "author": "",
                "file": str(py_file),
                "style": "legacy",
                "tags": [],
                "dependencies": [],
            }

        return None

    @staticmethod
    def _find_plugin_class(mod: Any) -> Optional[type]:
        """Find the first BasePlugin subclass defined in a module."""
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(obj, BasePlugin)
                and obj is not BasePlugin
                and hasattr(obj, "meta")
            ):
                return obj
        return None

    # -- Loading ------------------------------------------------------------

    def load(self, name: str) -> bool:
        """Load a plugin by filename stem (without .py).

        Imports the module, instantiates the plugin class (or wraps legacy),
        and transitions it to LOADED state. Does **not** enable it yet.
        """
        if name in self.plugins:
            log.warning("Plugin '%s' is already loaded.", name)
            return True

        py_file = self._plugins_dir / f"{name}.py"
        if not py_file.exists():
            log.error("Plugin file not found: %s", py_file)
            return False

        try:
            mod_name = f"plugins.{name}"
            spec = importlib.util.spec_from_file_location(mod_name, str(py_file))
            if not spec or not spec.loader:
                log.error("Cannot create module spec for %s", py_file)
                return False

            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)

            plugin_cls = self._find_plugin_class(mod)
            if plugin_cls is not None:
                plugin = plugin_cls()
            else:
                plugin = _LegacyPluginWrapper(mod, str(py_file))

            plugin.state = PluginState.LOADED
            self.plugins[plugin.meta.name] = plugin

            log.info(
                "Plugin loaded: %s v%s [%s]",
                plugin.meta.name,
                plugin.meta.version,
                "class" if plugin_cls else "legacy",
            )
            return True

        except Exception as exc:
            log.error("Failed to load plugin '%s': %s", name, exc)
            return False

    # -- Enabling -----------------------------------------------------------

    def enable(self, name: str) -> bool:
        """Enable a loaded plugin — calls on_enable() with a ToolkitContext.

        If the plugin is not yet loaded, attempts to load it first.
        Resolves dependencies before enabling.
        """
        if name not in self.plugins:
            if not self.load(name):
                return False

        plugin = self.plugins[name]

        if plugin.state == PluginState.ENABLED:
            log.info("Plugin '%s' is already enabled.", name)
            return True

        # Dependency check
        for dep in plugin.meta.dependencies:
            if dep not in self.plugins or self.plugins[dep].state != PluginState.ENABLED:
                log.info("Enabling dependency '%s' for plugin '%s'.", dep, name)
                if not self.enable(dep):
                    plugin._error = f"Dependency '{dep}' failed to enable."
                    plugin.state = PluginState.ERROR
                    log.error("Plugin '%s' dependency '%s' unavailable.", name, dep)
                    return False

        ctx = ToolkitContext(
            config=self._config,
            event_bus=self.event_bus,
            logger=get_logger(f"plugins.{name}"),
            plugin_name=name,
        )

        try:
            plugin.on_enable(ctx)
            plugin._ctx = ctx
            plugin.state = PluginState.ENABLED
            plugin._error = None

            self._persist_plugin(plugin, enabled=True)
            audit("plugin_enabled", name)
            self.event_bus.emit("plugin.enabled", plugin_name=name)

            log.info("Plugin enabled: %s v%s", plugin.meta.name, plugin.meta.version)
            return True

        except Exception as exc:
            plugin._error = str(exc)
            plugin.state = PluginState.ERROR
            log.error("Plugin '%s' on_enable() failed: %s", name, exc)
            return False

    # -- Disabling ----------------------------------------------------------

    def disable(self, name: str) -> bool:
        """Disable an enabled plugin — calls on_disable() and removes subscriptions."""
        if name not in self.plugins:
            log.warning("Plugin '%s' is not loaded.", name)
            return False

        plugin = self.plugins[name]
        if plugin.state != PluginState.ENABLED:
            log.info("Plugin '%s' is not enabled (state=%s).", name, plugin.state.name)
            return True

        # Check if other enabled plugins depend on this one
        for other_name, other in self.plugins.items():
            if (
                other.state == PluginState.ENABLED
                and name in other.meta.dependencies
            ):
                log.warning(
                    "Cannot disable '%s' — '%s' depends on it.", name, other_name
                )
                return False

        try:
            plugin.on_disable()
        except Exception as exc:
            log.warning("Plugin '%s' on_disable() error: %s", name, exc)

        # Remove all event subscriptions owned by this plugin
        removed = self.event_bus.unsubscribe_all(name)
        if removed:
            log.debug("Removed %d event subscriptions for '%s'.", removed, name)

        plugin.state = PluginState.DISABLED
        self._persist_plugin(plugin, enabled=False)
        audit("plugin_disabled", name)
        self.event_bus.emit("plugin.disabled", plugin_name=name)

        log.info("Plugin disabled: %s", name)
        return True

    # -- Unloading ----------------------------------------------------------

    def unload(self, name: str) -> bool:
        """Unload a plugin — disables it first if needed, then removes from memory."""
        if name not in self.plugins:
            log.warning("Plugin '%s' is not loaded.", name)
            return False

        plugin = self.plugins[name]

        if plugin.state == PluginState.ENABLED:
            if not self.disable(name):
                return False

        try:
            plugin.on_unload()
        except Exception as exc:
            log.warning("Plugin '%s' on_unload() error: %s", name, exc)

        del self.plugins[name]

        # Remove from sys.modules
        mod_name = f"plugins.{name}"
        sys.modules.pop(mod_name, None)

        audit("plugin_unloaded", name)
        self.event_bus.emit("plugin.unloaded", plugin_name=name)
        log.info("Plugin unloaded: %s", name)
        return True

    # -- Bulk operations ----------------------------------------------------

    def load_all(self) -> dict[str, bool]:
        """Discover and load all available plugins. Returns name → success map."""
        results: dict[str, bool] = {}
        for info in self.discover():
            name = info["name"]
            results[name] = self.load(name)
        return results

    def enable_all(self) -> dict[str, bool]:
        """Enable all loaded plugins. Returns name → success map."""
        results: dict[str, bool] = {}
        for name in list(self.plugins):
            results[name] = self.enable(name)
        return results

    def disable_all(self) -> dict[str, bool]:
        """Disable all enabled plugins (reverse dependency order)."""
        results: dict[str, bool] = {}
        for name in reversed(list(self.plugins)):
            if self.plugins[name].state == PluginState.ENABLED:
                results[name] = self.disable(name)
        return results

    def unload_all(self) -> dict[str, bool]:
        """Unload all plugins."""
        results: dict[str, bool] = {}
        for name in list(self.plugins):
            results[name] = self.unload(name)
        return results

    # -- Query --------------------------------------------------------------

    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        return self.plugins.get(name)

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with status."""
        return [p.to_dict() for p in self.plugins.values()]

    def get_all_routes(self) -> list[dict]:
        """Collect all dashboard routes registered by enabled plugins."""
        routes: list[dict] = []
        for p in self.plugins.values():
            if p.state == PluginState.ENABLED and p._ctx:
                routes.extend(p._ctx.routes)
        return routes

    def get_all_tools(self) -> list[dict]:
        """Collect all MCP tools registered by enabled plugins."""
        tools: list[dict] = []
        for p in self.plugins.values():
            if p.state == PluginState.ENABLED and p._ctx:
                tools.extend(p._ctx.tools)
        return tools

    # -- Persistence --------------------------------------------------------

    def _persist_plugin(self, plugin: BasePlugin, enabled: bool) -> None:
        """Upsert plugin record in the database."""
        try:
            existing = db.execute(
                "SELECT id FROM plugins WHERE name = ?", (plugin.meta.name,)
            )
            config_json = json.dumps(plugin.get_config_defaults())
            if existing:
                db.execute(
                    "UPDATE plugins SET version = ?, enabled = ?, config = ? WHERE name = ?",
                    (plugin.meta.version, int(enabled), config_json, plugin.meta.name),
                )
            else:
                db.insert("plugins", {
                    "name": plugin.meta.name,
                    "version": plugin.meta.version,
                    "enabled": int(enabled),
                    "config": config_json,
                })
        except Exception as exc:
            log.debug("DB persist for plugin '%s' failed: %s", plugin.meta.name, exc)

    def load_enabled_from_db(self) -> dict[str, bool]:
        """Load and enable all plugins marked as enabled in the database."""
        results: dict[str, bool] = {}
        try:
            rows = db.execute("SELECT name FROM plugins WHERE enabled = 1")
            for row in rows:
                name = row[0] if isinstance(row, (tuple, list)) else row["name"]
                results[name] = self.enable(name)
        except Exception as exc:
            log.debug("load_enabled_from_db: %s", exc)
        return results

    # -- Plugin scaffolding -------------------------------------------------

    def create_plugin_scaffold(self, name: str, author: str = "") -> str:
        """Generate a new plugin file from template. Returns the file path."""
        safe_name = name.replace("-", "_").replace(" ", "_").lower()
        class_name = "".join(w.capitalize() for w in safe_name.split("_")) + "Plugin"
        py_file = self._plugins_dir / f"{safe_name}.py"

        if py_file.exists():
            raise FileExistsError(f"Plugin file already exists: {py_file}")

        content = f'''"""Plugin: {name}"""
from plugins.base import BasePlugin, PluginMeta, ToolkitContext


class {class_name}(BasePlugin):
    """TODO: Describe what this plugin does."""

    meta = PluginMeta(
        name="{safe_name}",
        version="0.1.0",
        description="TODO: Add description",
        author="{author}",
        tags=[],
        dependencies=[],
    )

    def on_enable(self, ctx: ToolkitContext) -> None:
        self._ctx = ctx
        ctx.log.info("{class_name} enabled!")
        # Subscribe to events:
        # ctx.subscribe("audit.completed", self._on_audit_done)
        # Register dashboard routes:
        # ctx.register_route("/api/plugins/{safe_name}/status", "GET", self._status_handler)
        # Register MCP tools:
        # ctx.register_tool("my_tool", "Description", {{}}, self._tool_handler)

    def on_disable(self) -> None:
        if self._ctx:
            self._ctx.log.info("{class_name} disabled.")

    def get_status(self) -> dict:
        return {{**super().get_status(), "custom_field": "value"}}
'''
        py_file.write_text(content, encoding="utf-8")
        log.info("Created plugin scaffold: %s", py_file)
        return str(py_file)

    def __repr__(self) -> str:
        enabled = sum(1 for p in self.plugins.values() if p.state == PluginState.ENABLED)
        return f"<PluginManager loaded={len(self.plugins)} enabled={enabled}>"


# ---------------------------------------------------------------------------
# Singleton & backwards-compatible public API
# ---------------------------------------------------------------------------

manager = PluginManager()


def discover_plugins() -> list[dict]:
    """Discover all plugin modules in the plugins directory."""
    return manager.discover()


def load_plugin(name: str) -> bool:
    """Load and enable a plugin by name (backwards-compatible)."""
    return manager.enable(name)


def unload_plugin(name: str) -> bool:
    """Unload a plugin."""
    return manager.unload(name)


def get_loaded() -> dict[str, Any]:
    """Return all loaded plugins (backwards-compatible)."""
    return {name: p for name, p in manager.plugins.items()}
