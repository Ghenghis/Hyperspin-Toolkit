# Plugin Development Guide

## HyperSpin Extreme Toolkit — Plugin API v2.0

This guide covers everything you need to build, test, and distribute plugins for the HyperSpin Extreme Toolkit.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Plugin Architecture](#plugin-architecture)
3. [Creating a Plugin](#creating-a-plugin)
4. [Plugin Lifecycle](#plugin-lifecycle)
5. [ToolkitContext API](#toolkitcontext-api)
6. [Event System](#event-system)
7. [Dashboard Routes](#dashboard-routes)
8. [MCP Tools](#mcp-tools)
9. [Configuration](#configuration)
10. [Dependencies](#dependencies)
11. [Database Access](#database-access)
12. [CLI Commands](#cli-commands)
13. [REST API Endpoints](#rest-api-endpoints)
14. [Testing Your Plugin](#testing-your-plugin)
15. [Best Practices](#best-practices)
16. [Troubleshooting](#troubleshooting)
17. [API Reference](#api-reference)

---

## Quick Start

Generate a scaffold and enable it in under a minute:

```bash
# Generate a new plugin from template
python main.py plugin create my_plugin --author "Your Name"

# Edit the generated file
# plugins/my_plugin.py

# Enable it
python main.py plugin enable my_plugin

# Verify
python main.py plugin info my_plugin
```

---

## Plugin Architecture

### Overview

```
plugins/
├── __init__.py          # PluginManager — discovery, loading, lifecycle
├── base.py              # BasePlugin, ToolkitContext, EventBus, PluginMeta
├── example_plugin.py    # Reference implementation
└── your_plugin.py       # Your plugin here
```

### Key Components

- **BasePlugin** — Abstract base class every plugin extends
- **PluginMeta** — Dataclass holding plugin metadata (name, version, author, tags, etc.)
- **ToolkitContext** — Sandboxed API giving plugins safe access to config, database, logging, and events
- **EventBus** — Thread-safe publish/subscribe system for inter-plugin communication
- **PluginManager** — Singleton that handles discovery, loading, enabling, disabling, and unloading

### Lifecycle States

```
DISCOVERED → LOADED → ENABLED ⇄ DISABLED → (unloaded)
                 ↘ ERROR
```

| State        | Meaning                                                       |
| ------------ | ------------------------------------------------------------- |
| `DISCOVERED` | File found on disk, not yet imported                          |
| `LOADED`     | Module imported, plugin class instantiated                    |
| `ENABLED`    | `on_enable()` called, plugin is active                        |
| `DISABLED`   | `on_disable()` called, plugin is inactive but still in memory |
| `ERROR`      | An error occurred during load or enable                       |

---

## Creating a Plugin

### Minimal Plugin

```python
"""My Plugin — does something useful."""
from plugins.base import BasePlugin, PluginMeta, ToolkitContext

class MyPlugin(BasePlugin):
    meta = PluginMeta(
        name="my_plugin",
        version="1.0.0",
        description="A useful plugin",
        author="Your Name",
    )

    def on_enable(self, ctx: ToolkitContext) -> None:
        self._ctx = ctx
        ctx.log.info("my_plugin enabled!")

    def on_disable(self) -> None:
        if self._ctx:
            self._ctx.log.info("my_plugin disabled")
```

### Important Rules

1. Your plugin file must be placed in `plugins/` directory
2. The file must contain a class that extends `BasePlugin` with a `meta` attribute
3. The `meta` attribute must be a `PluginMeta` instance
4. The class must implement `on_enable(self, ctx: ToolkitContext) -> None`
5. The `PluginManager` calls `on_enable(ctx)` with a fresh `ToolkitContext` — store it as `self._ctx`

### Using the Scaffold Generator

```bash
python main.py plugin create rom_cleaner --author "Jane Dev"
```

This creates `plugins/rom_cleaner.py` with a complete template including all optional methods stubbed out.

---

## Plugin Lifecycle

### on_enable(ctx) → None

Called when the plugin is activated. The `ToolkitContext` is passed as an argument.
Use this to:
- Store the context reference
- Subscribe to events
- Register dashboard routes and MCP tools
- Initialize state

If this method raises an exception, the plugin transitions to ERROR state.

```python
def on_enable(self, ctx: ToolkitContext) -> None:
    self._ctx = ctx
    ctx.subscribe("audit.completed", self._on_audit)
    ctx.register_route("/api/plugins/my_plugin/status", "GET", self._api_status)
    self._cache = {}
```

### on_disable() → None

Called when the plugin is deactivated. Use this to:
- Release resources
- Save state

Note: Event subscriptions registered via `ctx.subscribe()` are automatically
removed by the PluginManager — you only need to override this for custom cleanup.

```python
def on_disable(self) -> None:
    self._cache.clear()
```

### get_status() → dict

Optional. Return a dict with runtime status information. Shown in `plugin info` and the dashboard.
The base implementation returns `{name, version, state, error}`.

```python
def get_status(self) -> dict:
    base = super().get_status()
    base["items_processed"] = self._count
    base["cache_size"] = len(self._cache)
    base["healthy"] = True
    return base
```

### get_config_defaults() → dict

Optional. Return default configuration values. These are stored in the database and can be modified via the REST API.

```python
def get_config_defaults(self) -> dict:
    return {
        "scan_interval_sec": 300,
        "max_items": 1000,
        "auto_fix": False,
    }
```

---

## ToolkitContext API

Every plugin receives a `ToolkitContext` as the argument to `on_enable(ctx)`. Store it as `self._ctx` and use it for all interaction with the toolkit.

### Available Methods

| Method                                           | Description                               |
| ------------------------------------------------ | ----------------------------------------- |
| `ctx.get_config(dotpath, default=None)`          | Dot-notation config access                |
| `ctx.config`                                     | Full config dict (read-only property)     |
| `ctx.db_execute(sql, params=())`                 | Execute read-only SQL query               |
| `ctx.db_insert(table, data)`                     | Insert into `plugin_*` tables only        |
| `ctx.log`                                        | Logger scoped to the plugin name          |
| `ctx.events`                                     | Direct access to the shared EventBus      |
| `ctx.subscribe(event, callback)`                 | Subscribe (auto-tagged with plugin owner) |
| `ctx.emit(event, **data)`                        | Emit event (auto-prefixed if bare)        |
| `ctx.audit(action, detail, **extra)`             | Write audit trail entry                   |
| `ctx.register_route(path, method, handler)`      | Register dashboard route                  |
| `ctx.register_tool(name, desc, schema, handler)` | Register MCP tool                         |
| `ctx.get_engine(name)`                           | Import a toolkit engine module            |

### Config Access

```python
hs_root = self._ctx.get_config("paths.hyperspin_root")
ai_url = self._ctx.get_config("ai.lmstudio_url", "http://localhost:1234/v1")
full_cfg = self._ctx.config  # returns full dict copy
```

### Database Access

```python
# Read-only queries (SELECT only)
systems = self._ctx.db_execute(
    "SELECT name, rom_count FROM systems WHERE rom_count > ?", (100,)
)
for s in systems:
    self._ctx.log.info(f"{s['name']}: {s['rom_count']} ROMs")

# Write to plugin_* tables only
self._ctx.db_insert("plugin_events", {
    "plugin_name": self.meta.name,
    "event_type": "scan_complete",
    "details": f"Scanned {count} files",
})
```

> **Security**: `db_execute()` blocks non-SELECT queries. `db_insert()` only allows writes to tables prefixed with `plugin_`. This protects core toolkit data.

### Logging

```python
self._ctx.log.info("Processing started")
self._ctx.log.warning("File not found: %s", path)
self._ctx.log.error("Failed to parse: %s", exc)
```

The logger is pre-configured with the plugin name as its namespace (e.g. `plugins.my_plugin`).

---

## Event System

The EventBus enables decoupled communication between plugins and the toolkit core.

### Subscribing to Events

```python
def on_enable(self, ctx: ToolkitContext) -> None:
    self._ctx = ctx
    ctx.subscribe("audit.completed", self._handle_audit)
    ctx.subscribe("backup.completed", self._handle_backup)

def _handle_audit(self, **data):
    score = data.get("health_score", 0)
    self._ctx.log.info(f"Audit complete, score: {score}")
```

### Emitting Events

Events use `**kwargs`, not a positional dict:

```python
self._ctx.emit("scan_complete", files_scanned=42, issues_found=3)
# Auto-prefixed to: my_plugin.scan_complete

# Or use the event bus directly:
self._ctx.events.emit("my_plugin.scan_complete", files_scanned=42, issues_found=3)
```

### Unsubscribing

Event subscriptions registered via `ctx.subscribe()` are **automatically removed**
when the plugin is disabled (the PluginManager calls `event_bus.unsubscribe_all(owner)`).
You only need to manually unsubscribe if you used `ctx.events.subscribe()` directly.

### Built-in Events

| Event                | Data                        | Emitted When           |
| -------------------- | --------------------------- | ---------------------- |
| `plugin.enabled`     | `plugin_name=str`           | A plugin is enabled    |
| `plugin.disabled`    | `plugin_name=str`           | A plugin is disabled   |
| `plugin.unloaded`    | `plugin_name=str`           | A plugin is unloaded   |
| `audit.completed`    | `result=dict`               | Full audit finishes    |
| `backup.completed`   | `result=dict`               | Backup is completed    |
| `scan.completed`     | `system=str, rom_count=int` | System scan finishes   |
| `toolkit.init`       | (none)                      | Toolkit initialization |
| `toolkit.shutdown`   | (none)                      | Toolkit shutdown       |
| `dashboard.startup`  | (none)                      | Dashboard starts       |
| `dashboard.shutdown` | (none)                      | Dashboard stops        |

### Error Isolation

If your event handler raises an exception, it is caught and logged — other listeners and the emitter are not affected. This is by design to prevent one plugin from crashing the system.

---

## Dashboard Routes

Plugins register REST endpoints via `ctx.register_route()` during `on_enable()`.

```python
def on_enable(self, ctx: ToolkitContext) -> None:
    self._ctx = ctx
    ctx.register_route(
        path="/api/plugins/my_plugin/status",
        method="GET",
        handler=self._api_status,
        summary="Get my_plugin status",
    )
    ctx.register_route(
        path="/api/plugins/my_plugin/run",
        method="POST",
        handler=self._api_run,
        summary="Trigger my_plugin action",
    )

async def _api_status(self, request):
    return {"status": "ok", "count": self._count}

async def _api_run(self, request):
    self._do_work()
    return {"triggered": True}
```

Routes are collected via `PluginManager.get_all_routes()` and mounted by the dashboard.

---

## MCP Tools

Plugins register MCP tools via `ctx.register_tool()` during `on_enable()`.
Tool names are auto-prefixed with `plugin_{plugin_name}_`.

```python
def on_enable(self, ctx: ToolkitContext) -> None:
    self._ctx = ctx
    ctx.register_tool(
        name="analyze",
        description="Analyze ROM directory with my_plugin",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to scan"},
                "deep": {"type": "boolean", "description": "Deep scan mode"},
            },
            "required": ["path"],
        },
        handler=self._tool_analyze,
    )

def _tool_analyze(self, **args) -> dict:
    path = args.get("path", ".")
    deep = args.get("deep", False)
    results = self._scan(path, deep=deep)
    return {"files": len(results), "issues": self._count_issues(results)}
```

The registered tool name becomes `plugin_my_plugin_analyze`. Tools are collected via
`PluginManager.get_all_tools()` and are available through:
- MCP Bridge (`tools/list` and `tools/call`)
- REST API (`/api/plugins/{name}/tools`)
- CLI (`plugin_call_tool` MCP tool)

---

## Configuration

### Defining Defaults

```python
def get_config_defaults(self) -> dict:
    return {
        "scan_interval": 300,
        "auto_fix": False,
        "exclusions": ["*.tmp", "*.bak"],
    }
```

### Reading Config at Runtime

Plugin config is stored in the `plugin_config` database table:

```python
rows = self._ctx.db_execute(
    "SELECT key, value FROM plugin_config WHERE plugin_name=?",
    ("my_plugin",)
)
config = {r["key"]: r["value"] for r in rows}
```

### Updating Config via REST API

```
PUT /api/plugins/my_plugin/config
Content-Type: application/json

{"scan_interval": "600", "auto_fix": "true"}
```

---

## Dependencies

Declare dependencies on other plugins:

```python
meta = PluginMeta(
    name="advanced_scanner",
    version="1.0.0",
    description="Advanced ROM scanner",
    dependencies=["rom_hasher", "database_helper"],
)
```

The PluginManager resolves dependencies automatically:
- When enabling `advanced_scanner`, `rom_hasher` and `database_helper` are enabled first
- When disabling `rom_hasher`, any plugins that depend on it are warned

---

## Database Access

### Plugin Tables

The toolkit provides these plugin-specific tables:

| Table                 | Purpose                                  |
| --------------------- | ---------------------------------------- |
| `plugins`             | Plugin registry with metadata and state  |
| `plugin_config`       | Key-value config store per plugin        |
| `plugin_dependencies` | Dependency relationships                 |
| `plugin_hooks`        | Registered hooks (events, routes, tools) |
| `plugin_events`       | Lifecycle event log                      |

### Writing to the Database

Use `ctx.db_insert()` which is restricted to `plugin_*` tables for safety:

```python
self._ctx.db_insert("plugin_events", {
    "plugin_name": self.meta.name,
    "event_type": "scan_complete",
    "details": f"Scanned {count} files",
})

self._ctx.db_insert("plugin_config", {
    "plugin_name": self.meta.name,
    "key": "last_run",
    "value": "2025-03-17T08:00:00Z",
})
```

---

## CLI Commands

All plugin management is available from the command line:

```bash
# List loaded plugins
python main.py plugin list

# List all discovered plugins (including unloaded)
python main.py plugin list --all

# Enable a plugin
python main.py plugin enable my_plugin

# Disable a plugin
python main.py plugin disable my_plugin

# Unload from memory
python main.py plugin unload my_plugin

# Show detailed info
python main.py plugin info my_plugin

# Create new plugin from template
python main.py plugin create my_plugin --author "Name"

# Show event bus subscriptions
python main.py plugin events

# Enable all discovered plugins
python main.py plugin load-all
```

---

## REST API Endpoints

The dashboard exposes these endpoints for plugin management:

| Method | Path                          | Description                |
| ------ | ----------------------------- | -------------------------- |
| `GET`  | `/api/plugins`                | List all loaded plugins    |
| `POST` | `/api/plugins/discover`       | Discover available plugins |
| `POST` | `/api/plugins/{name}/enable`  | Enable a plugin            |
| `POST` | `/api/plugins/{name}/disable` | Disable a plugin           |
| `POST` | `/api/plugins/{name}/unload`  | Unload a plugin            |
| `GET`  | `/api/plugins/{name}/info`    | Get plugin details         |
| `POST` | `/api/plugins/create`         | Create plugin scaffold     |
| `GET`  | `/api/plugins/events`         | List event subscriptions   |

---

## Testing Your Plugin

### Running the Plugin Test Suite

```bash
python tests/test_plugins.py
```

### Writing Tests for Your Plugin

```python
import logging
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from plugins.base import EventBus, ToolkitContext

def test_my_plugin():
    from plugins.my_plugin import MyPlugin

    bus = EventBus()
    ctx = ToolkitContext(
        config={},
        event_bus=bus,
        logger=logging.getLogger("test.my_plugin"),
        plugin_name="my_plugin",
    )
    p = MyPlugin()
    p.on_enable(ctx)

    status = p.get_status()
    assert status["healthy"] is True
    p.on_disable()
    print("[PASS] my_plugin works")
```

### Test Categories

The test suite (`tests/test_plugins.py`) covers:

- **EventBus** — subscribe, emit, unsubscribe, unsubscribe_all, error isolation
- **ToolkitContext** — creation, get_config, db_execute, db_insert, write blocking, register_tool, register_route
- **BasePlugin** — metadata, subclassing, to_dict, get_config_defaults, get_status
- **PluginManager** — discover, load, enable, disable, unload, scaffold, load_enabled_from_db
- **Database** — plugin tables, config CRUD, events log, dependencies, hooks
- **Integration** — full lifecycle, cross-plugin event flow

---

## Best Practices

### Do

- Store `ctx` as `self._ctx` in `on_enable()`
- Return meaningful data from `get_status()`
- Use `self._ctx.log` for all logging (not `print()`)
- Declare dependencies explicitly in `PluginMeta`
- Handle exceptions gracefully in event handlers
- Use `config_defaults()` for all configurable values
- Name your MCP tools with a plugin prefix (e.g., `my_plugin_analyze`)

### Don't

- Don't use global mutable state outside your plugin class
- Don't import heavy libraries at module level — use lazy imports in methods
- Don't write directly to toolkit tables (systems, roms, emulators) — use events
- Don't block the event loop in async dashboard route handlers
- Don't hardcode paths — use `self._ctx.get_config()` and `self._ctx.get_engine()`

### Naming Conventions

| Item         | Convention                | Example                      |
| ------------ | ------------------------- | ---------------------------- |
| Plugin file  | `snake_case.py`           | `rom_cleaner.py`             |
| Plugin class | Any `BasePlugin` subclass | `class MyPlugin(BasePlugin)` |
| Meta name    | matches filename stem     | `name="rom_cleaner"`         |
| MCP tools    | `pluginname_action`       | `rom_cleaner_scan`           |
| Events       | `pluginname.action`       | `rom_cleaner.scan_complete`  |
| API routes   | `/api/pluginname/...`     | `/api/rom_cleaner/status`    |

### Code Quality

- Follow PEP 8 style conventions
- Type-hint all public methods
- Include a module-level docstring describing the plugin
- Keep `on_enable()` fast — defer heavy initialization to first use
- Use structured logging with format strings, not f-strings in log calls

---

## Troubleshooting

### Plugin Won't Load

1. Check the file is in `plugins/` and ends with `.py`
2. Verify it contains a class that extends `BasePlugin` with a `meta` attribute
3. Check for import errors: `python -c "import plugins.my_plugin"`
4. Look at toolkit logs: `data/logs/toolkit.log`

### Plugin Loads But Won't Enable

1. `on_enable(ctx)` must not raise an exception
2. Check for missing dependencies
3. Look for exceptions in the log
4. Run `plugin info my_plugin` to see the error field

### Events Not Firing

1. Verify you subscribed in `on_enable()` with the exact event name
2. Check `plugin events` CLI to see active subscriptions
3. Ensure the emitter is using the same event name string
4. Check for exceptions in your handler (they are caught silently)

### MCP Tools Not Appearing

1. Verify you called `ctx.register_tool()` in `on_enable()`
2. Plugin must be in ENABLED state
3. Restart the MCP bridge after enabling a new plugin

### Dashboard Routes Not Working

1. Verify you called `ctx.register_route()` in `on_enable()`
2. Routes are collected at dashboard startup — restart the dashboard after enabling
3. Check for conflicting route paths

---

## API Reference

### PluginMeta

```python
@dataclass
class PluginMeta:
    name: str                    # Unique plugin identifier
    version: str                 # Semver string
    description: str = ""        # Human-readable description
    author: str = ""             # Author name
    url: str = ""                # Project URL
    license: str = ""            # License identifier
    min_toolkit: str = "2.0.0"   # Minimum toolkit version
    dependencies: list[str] = [] # Required plugin names
    tags: list[str] = []         # Categorization tags
```

### BasePlugin

```python
class BasePlugin(ABC):
    meta: PluginMeta             # Class attribute — must be set by subclass
    state: PluginState           # Current lifecycle state (managed by PluginManager)
    context: ToolkitContext      # Set after on_enable() via plugin._ctx
    error: str | None            # Error message if in ERROR state

    # Required
    def on_enable(self, ctx: ToolkitContext) -> None: ...

    # Optional
    def on_disable(self) -> None: ...
    def on_unload(self) -> None: ...
    def get_status(self) -> dict: ...
    def get_config_defaults(self) -> dict: ...
    def to_dict(self) -> dict: ...
```

### EventBus

```python
class EventBus:
    def subscribe(event: str, callback: Callable, owner: str = None) -> None
    def unsubscribe(event: str, callback: Callable) -> None
    def unsubscribe_all(owner: str) -> int
    def emit(event: str, **data) -> None
    def list_events() -> list[str]
    def listener_count(event: str) -> int
```

### ToolkitContext

```python
class ToolkitContext:
    def __init__(*, config: dict, event_bus: EventBus,
                 logger: Logger, plugin_name: str = "")

    # Properties
    config: dict                 # Full config (read-only copy)
    events: EventBus             # Shared event bus
    log: Logger                  # Plugin-scoped logger

    # Config
    def get_config(dotpath: str, default=None) -> Any

    # Events
    def subscribe(event: str, callback: Callable) -> None
    def emit(event: str, **data) -> None

    # Database
    def db_execute(sql: str, params=()) -> list  # SELECT only
    def db_insert(table: str, data: dict) -> int  # plugin_* tables only

    # Audit
    def audit(action: str, detail: str = "", **extra) -> None

    # Registration
    def register_route(path, method, handler, summary="") -> None
    def register_tool(name, description, input_schema, handler) -> None
    routes: list[dict]           # Registered routes
    tools: list[dict]            # Registered tools

    # Engines
    def get_engine(name: str) -> module | None
```

### PluginManager

```python
class PluginManager:
    def __init__(config: dict = None)
    event_bus: EventBus          # Shared event bus
    plugins: dict[str, BasePlugin]

    def set_config(config: dict) -> None
    def discover() -> list[dict]
    def load(name: str) -> bool
    def enable(name: str) -> bool
    def disable(name: str) -> bool
    def unload(name: str) -> bool
    def get_plugin(name: str) -> BasePlugin | None
    def list_plugins() -> list[dict]
    def get_all_tools() -> list[dict]
    def get_all_routes() -> list[dict]
    def load_all() -> dict[str, bool]
    def enable_all() -> dict[str, bool]
    def disable_all() -> dict[str, bool]
    def unload_all() -> dict[str, bool]
    def load_enabled_from_db() -> dict[str, bool]
    def create_plugin_scaffold(name: str, author: str = "") -> str
```

---

## Legacy Plugin Support

The toolkit maintains backward compatibility with older module-level plugins that use:

```python
PLUGIN_NAME = "old_plugin"
PLUGIN_VERSION = "1.0"
PLUGIN_DESCRIPTION = "A legacy plugin"

def register(toolkit):
    pass

def unregister():
    pass
```

These are automatically wrapped in a `LegacyPluginWrapper` and participate in the same lifecycle as class-based plugins. However, new plugins should always use the class-based API for full feature access.
