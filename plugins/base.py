"""Plugin API Foundation — BasePlugin, ToolkitContext, and EventBus.

Provides the core abstractions for the HyperSpin Extreme Toolkit plugin system:

  - **EventBus**:       Pub/sub event system for decoupled communication.
  - **ToolkitContext**:  Sandboxed interface plugins use to interact with core.
  - **BasePlugin**:      Abstract base class every plugin must subclass.

Plugin Lifecycle:
  1. Discovery  — PluginManager scans plugins/ for BasePlugin subclasses
  2. Load       — Module imported, plugin class instantiated
  3. Enable     — on_enable() called, event subscriptions activated
  4. Disable    — on_disable() called, subscriptions removed
  5. Unload     — on_unload() called, module removed from sys.modules
"""
from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Plugin State
# ---------------------------------------------------------------------------

class PluginState(Enum):
    """Lifecycle states a plugin can be in."""
    DISCOVERED = auto()
    LOADED     = auto()
    ENABLED    = auto()
    DISABLED   = auto()
    ERROR      = auto()


# ---------------------------------------------------------------------------
# Plugin Metadata
# ---------------------------------------------------------------------------

@dataclass
class PluginMeta:
    """Declarative metadata every plugin must provide."""
    name:         str
    version:      str
    description:  str = ""
    author:       str = ""
    url:          str = ""
    license:      str = ""
    min_toolkit:  str = "2.0.0"
    dependencies: list[str] = field(default_factory=list)
    tags:         list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "url": self.url,
            "license": self.license,
            "min_toolkit": self.min_toolkit,
            "dependencies": self.dependencies,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

EventCallback = Callable[..., Any]


class EventBus:
    """Thread-safe publish/subscribe event bus.

    Built-in events emitted by the toolkit core:

        plugin.loaded        (plugin_name: str)
        plugin.enabled       (plugin_name: str)
        plugin.disabled      (plugin_name: str)
        plugin.unloaded      (plugin_name: str)
        audit.started        ()
        audit.completed      (result: dict)
        backup.started       (path: str, label: str)
        backup.completed     (result: dict)
        update.available     (emulator: str, current: str, latest: str)
        update.applied       (emulator: str, version: str)
        scan.completed       (system: str, rom_count: int)
        dashboard.startup    ()
        dashboard.shutdown   ()
        toolkit.init         ()
        toolkit.shutdown     ()

    Plugins may also emit and subscribe to custom events (prefix with
    your plugin name, e.g. ``myplugin.data_ready``).
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[tuple[EventCallback, Optional[str]]]] = {}
        self._lock = threading.Lock()

    # -- subscribe / unsubscribe --------------------------------------------

    def subscribe(
        self,
        event: str,
        callback: EventCallback,
        owner: Optional[str] = None,
    ) -> None:
        """Register *callback* to be called when *event* is emitted.

        Args:
            event:    Dotted event name (e.g. ``audit.completed``).
            callback: Callable invoked with ``(**data)`` when the event fires.
            owner:    Optional owner tag (plugin name) for bulk removal.
        """
        with self._lock:
            self._listeners.setdefault(event, []).append((callback, owner))

    def unsubscribe(self, event: str, callback: EventCallback) -> None:
        """Remove a specific callback from *event*."""
        with self._lock:
            lst = self._listeners.get(event, [])
            self._listeners[event] = [(cb, o) for cb, o in lst if cb is not callback]

    def unsubscribe_all(self, owner: str) -> int:
        """Remove **all** callbacks registered under *owner*. Returns count removed."""
        removed = 0
        with self._lock:
            for event in list(self._listeners):
                before = len(self._listeners[event])
                self._listeners[event] = [
                    (cb, o) for cb, o in self._listeners[event] if o != owner
                ]
                removed += before - len(self._listeners[event])
        return removed

    # -- emit ---------------------------------------------------------------

    def emit(self, event: str, **data: Any) -> None:
        """Fire *event*, calling every registered listener with **data.

        Exceptions in listeners are logged but do **not** propagate.
        """
        log = logging.getLogger("plugins.eventbus")
        with self._lock:
            listeners = list(self._listeners.get(event, []))

        for callback, _owner in listeners:
            try:
                callback(**data)
            except Exception as exc:
                log.warning(
                    "EventBus: listener %s for event '%s' raised %s: %s",
                    getattr(callback, "__qualname__", callback),
                    event,
                    type(exc).__name__,
                    exc,
                )

    # -- introspection ------------------------------------------------------

    def list_events(self) -> list[str]:
        """Return all event names that have at least one subscriber."""
        with self._lock:
            return [e for e, lst in self._listeners.items() if lst]

    def listener_count(self, event: str) -> int:
        with self._lock:
            return len(self._listeners.get(event, []))

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._listeners.values())
        return f"<EventBus events={len(self._listeners)} listeners={total}>"


# ---------------------------------------------------------------------------
# Toolkit Context — the "API surface" plugins use
# ---------------------------------------------------------------------------

class ToolkitContext:
    """Sandboxed interface providing controlled access to toolkit internals.

    An instance is passed to every plugin during ``on_enable(ctx)``.
    Plugins should store it and use it for all interaction with the toolkit.
    """

    def __init__(
        self,
        *,
        config: dict,
        event_bus: EventBus,
        logger: logging.Logger,
        plugin_name: str = "",
    ) -> None:
        self._config = config
        self._event_bus = event_bus
        self._logger = logger
        self._plugin_name = plugin_name
        self._registered_routes: list[dict] = []
        self._registered_tools: list[dict] = []

    # -- Configuration (read-only) ------------------------------------------

    @property
    def config(self) -> dict:
        """Full toolkit configuration (read-only snapshot)."""
        return dict(self._config)

    def get_config(self, dotpath: str, default: Any = None) -> Any:
        """Dot-notation config access (e.g. ``ctx.get_config('backup.compress')``).

        Args:
            dotpath: Dot-separated path into the config dict.
            default: Value returned when the key is missing.
        """
        keys = dotpath.split(".")
        node: Any = self._config
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    # -- Logging & Audit ----------------------------------------------------

    @property
    def log(self) -> logging.Logger:
        """Logger scoped to the plugin name."""
        return self._logger

    def audit(self, action: str, detail: str = "", **extra: Any) -> None:
        """Write an audit-trail entry tagged with this plugin's name.

        Args:
            action: Short action verb (e.g. ``rom_cleaned``).
            detail: Human-readable detail string.
            **extra: Arbitrary JSON-serialisable key-value data.
        """
        try:
            from core.logger import audit as _audit
            details = {"message": detail, **extra} if detail or extra else None
            _audit(
                action=f"plugin.{self._plugin_name}.{action}",
                target=self._plugin_name,
                details=details,
            )
        except Exception as exc:
            self._logger.warning("Audit write failed: %s", exc)

    # -- Event Bus ----------------------------------------------------------

    @property
    def events(self) -> EventBus:
        """Direct access to the shared event bus."""
        return self._event_bus

    def subscribe(self, event: str, callback: EventCallback) -> None:
        """Subscribe to an event (auto-tagged with this plugin's owner)."""
        self._event_bus.subscribe(event, callback, owner=self._plugin_name)

    def emit(self, event: str, **data: Any) -> None:
        """Emit a custom event (auto-prefixed with plugin name if bare)."""
        if "." not in event:
            event = f"{self._plugin_name}.{event}"
        self._event_bus.emit(event, **data)

    # -- Database -----------------------------------------------------------

    def db_execute(self, sql: str, params: tuple = ()) -> list:
        """Execute a read-only SQL query against the toolkit database.

        Returns list of Row objects. Write operations are intentionally
        blocked to protect data integrity — use ``db_insert`` instead.
        """
        sql_upper = sql.strip().upper()
        if not sql_upper.startswith("SELECT"):
            raise PermissionError("Plugins may only execute SELECT queries via db_execute.")
        try:
            from core.database import execute
            return execute(sql, params)
        except Exception as exc:
            self._logger.error("db_execute failed: %s", exc)
            return []

    def db_insert(self, table: str, data: dict) -> Optional[int]:
        """Insert a row into an allowed table. Returns the new row id.

        Only tables prefixed with ``plugin_`` are writable by plugins.
        """
        if not table.startswith("plugin_"):
            raise PermissionError(
                f"Plugins may only write to 'plugin_*' tables, got '{table}'."
            )
        try:
            from core.database import insert
            return insert(table, data)
        except Exception as exc:
            self._logger.error("db_insert failed: %s", exc)
            return None

    # -- Dashboard Route Registration ---------------------------------------

    def register_route(
        self,
        path: str,
        method: str,
        handler: Callable,
        summary: str = "",
    ) -> None:
        """Register a custom HTTP route on the dashboard.

        Args:
            path:    URL path (e.g. ``/api/plugins/myplugin/status``).
            method:  HTTP method (``GET``, ``POST``, etc.).
            handler: Async or sync callable ``(request) -> response``.
            summary: Short description for OpenAPI docs.
        """
        route = {
            "path": path,
            "method": method.upper(),
            "handler": handler,
            "summary": summary,
            "plugin": self._plugin_name,
        }
        self._registered_routes.append(route)
        self._logger.debug("Registered route %s %s", method.upper(), path)

    @property
    def routes(self) -> list[dict]:
        return list(self._registered_routes)

    # -- MCP Tool Registration ----------------------------------------------

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: dict,
        handler: Callable,
    ) -> None:
        """Register a custom MCP tool exposed through mcp_bridge.

        Args:
            name:         Tool name (auto-prefixed with ``plugin_``).
            description:  Human-readable description.
            input_schema: JSON Schema for the tool's input.
            handler:      Callable receiving ``(**args) -> dict``.
        """
        tool_name = f"plugin_{self._plugin_name}_{name}"
        tool = {
            "name": tool_name,
            "description": f"[Plugin: {self._plugin_name}] {description}",
            "inputSchema": input_schema,
            "handler": handler,
            "plugin": self._plugin_name,
        }
        self._registered_tools.append(tool)
        self._logger.debug("Registered MCP tool: %s", tool_name)

    @property
    def tools(self) -> list[dict]:
        return list(self._registered_tools)

    # -- Engine Access (lazy imports to avoid circular deps) -----------------

    def get_engine(self, name: str) -> Any:
        """Import and return a toolkit engine module by short name.

        Supported names: ``scanner``, ``auditor``, ``backup``,
        ``update_manager``, ``ai_engine``, ``drive_manager``,
        ``release_checker``, ``space_optimizer``, ``external_tools``,
        ``drive_transfer``, ``llm_detector``.

        Returns:
            The engine module object, or ``None`` if not found.
        """
        engine_map = {
            "scanner":          "engines.scanner",
            "auditor":          "engines.auditor",
            "backup":           "engines.backup",
            "update_manager":   "engines.update_manager",
            "ai_engine":        "engines.ai_engine",
            "drive_manager":    "engines.drive_manager",
            "release_checker":  "engines.release_checker",
            "space_optimizer":  "engines.space_optimizer",
            "external_tools":   "engines.external_tools",
            "drive_transfer":   "engines.drive_transfer",
            "llm_detector":     "engines.llm_detector",
        }
        mod_path = engine_map.get(name)
        if not mod_path:
            self._logger.warning("Unknown engine: %s", name)
            return None
        try:
            import importlib
            return importlib.import_module(mod_path)
        except Exception as exc:
            self._logger.error("Failed to import engine '%s': %s", name, exc)
            return None

    def __repr__(self) -> str:
        return (
            f"<ToolkitContext plugin={self._plugin_name!r} "
            f"routes={len(self._registered_routes)} "
            f"tools={len(self._registered_tools)}>"
        )


# ---------------------------------------------------------------------------
# Base Plugin — abstract class every plugin must subclass
# ---------------------------------------------------------------------------

class BasePlugin(abc.ABC):
    """Abstract base class for HyperSpin Extreme Toolkit plugins.

    Subclasses **must** define ``meta`` (a :class:`PluginMeta` instance)
    and implement :meth:`on_enable`.

    Minimal plugin example::

        from plugins.base import BasePlugin, PluginMeta, ToolkitContext

        class MyPlugin(BasePlugin):
            meta = PluginMeta(
                name="my_plugin",
                version="1.0.0",
                description="Does something useful.",
                author="You",
            )

            def on_enable(self, ctx: ToolkitContext) -> None:
                ctx.log.info("MyPlugin enabled!")
                ctx.subscribe("audit.completed", self._on_audit)

            def _on_audit(self, **data):
                print("Audit finished:", data)
    """

    # Subclass MUST override this
    meta: PluginMeta

    def __init__(self) -> None:
        self._state: PluginState = PluginState.LOADED
        self._ctx: Optional[ToolkitContext] = None
        self._error: Optional[str] = None

    # -- Properties ---------------------------------------------------------

    @property
    def state(self) -> PluginState:
        return self._state

    @state.setter
    def state(self, value: PluginState) -> None:
        self._state = value

    @property
    def context(self) -> Optional[ToolkitContext]:
        return self._ctx

    @property
    def error(self) -> Optional[str]:
        return self._error

    # -- Lifecycle hooks (override as needed) -------------------------------

    @abc.abstractmethod
    def on_enable(self, ctx: ToolkitContext) -> None:
        """Called when the plugin is enabled. Set up subscriptions and routes here.

        Args:
            ctx: The ToolkitContext providing access to core functionality.
        """
        ...

    def on_disable(self) -> None:
        """Called when the plugin is disabled. Clean up resources here.

        Event subscriptions registered via ``ctx.subscribe()`` are
        automatically removed — you only need to override this for
        custom cleanup (file handles, background threads, etc.).
        """

    def on_unload(self) -> None:
        """Called just before the plugin module is removed from memory.

        Final cleanup opportunity. After this, the class instance is deleted.
        """

    def get_config_defaults(self) -> dict:
        """Return default plugin-specific configuration values.

        These are merged (underlay) with any user-supplied config stored
        in the database ``plugins`` table ``config`` column.
        """
        return {}

    def get_status(self) -> dict:
        """Return a status dict for dashboard / CLI display.

        Override to provide custom health or status information.
        """
        return {
            "name": self.meta.name,
            "version": self.meta.version,
            "state": self._state.name,
            "error": self._error,
        }

    # -- Convenience --------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise plugin info to a JSON-compatible dict."""
        return {
            **self.meta.to_dict(),
            "state": self._state.name,
            "error": self._error,
            "status": self.get_status(),
        }

    def __repr__(self) -> str:
        return (
            f"<Plugin {self.meta.name!r} v{self.meta.version} "
            f"state={self._state.name}>"
        )
