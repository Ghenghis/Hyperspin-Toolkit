"""Example Plugin — Demonstrates the full HyperSpin Extreme Toolkit Plugin API.

Shows how to:
  - Define metadata with PluginMeta
  - Subscribe to toolkit events
  - Register custom dashboard routes
  - Register custom MCP tools
  - Access toolkit engines and config
  - Provide plugin-specific config defaults
  - Report custom status information
"""
from __future__ import annotations

from plugins.base import BasePlugin, PluginMeta, ToolkitContext


class ExamplePlugin(BasePlugin):
    """Fully-featured example plugin showcasing the Plugin API."""

    meta = PluginMeta(
        name="example_plugin",
        version="1.0.0",
        description="Example plugin demonstrating the toolkit plugin API.",
        author="HyperSpin Toolkit Team",
        url="https://github.com/hyperspin-toolkit",
        license="MIT",
        tags=["example", "demo"],
        dependencies=[],
    )

    def __init__(self) -> None:
        super().__init__()
        self._audit_count = 0

    # -- Lifecycle ----------------------------------------------------------

    def on_enable(self, ctx: ToolkitContext) -> None:
        """Set up event listeners, routes, and tools."""
        self._ctx = ctx
        ctx.log.info("ExamplePlugin enabled!")

        # Subscribe to toolkit events
        ctx.subscribe("audit.completed", self._on_audit_completed)
        ctx.subscribe("backup.completed", self._on_backup_completed)
        ctx.subscribe("plugin.enabled", self._on_plugin_event)

        # Register a custom dashboard REST endpoint
        ctx.register_route(
            path="/api/plugins/example/status",
            method="GET",
            handler=self._api_status,
            summary="Get example plugin status",
        )

        # Register a custom MCP tool for AI agents
        ctx.register_tool(
            name="hello",
            description="A demo tool that returns a greeting.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name to greet"},
                },
                "required": ["name"],
            },
            handler=self._tool_hello,
        )

        ctx.audit("enabled", "ExamplePlugin started successfully")

    def on_disable(self) -> None:
        """Clean up resources."""
        if self._ctx:
            self._ctx.log.info(
                "ExamplePlugin disabled after tracking %d audits.", self._audit_count
            )

    def on_unload(self) -> None:
        """Final cleanup before removal from memory."""
        self._audit_count = 0

    # -- Configuration ------------------------------------------------------

    def get_config_defaults(self) -> dict:
        return {
            "greeting_prefix": "Hello",
            "track_audits": True,
            "max_log_entries": 100,
        }

    def get_status(self) -> dict:
        base = super().get_status()
        base["audits_tracked"] = self._audit_count
        base["subscriptions"] = ["audit.completed", "backup.completed", "plugin.enabled"]
        return base

    # -- Event Handlers -----------------------------------------------------

    def _on_audit_completed(self, **data) -> None:
        """React when a full audit finishes."""
        self._audit_count += 1
        if self._ctx:
            self._ctx.log.info(
                "ExamplePlugin: audit #%d completed — %s",
                self._audit_count,
                data.get("summary", "no summary"),
            )

    def _on_backup_completed(self, **data) -> None:
        if self._ctx:
            self._ctx.log.info("ExamplePlugin: backup completed — %s", data)

    def _on_plugin_event(self, **data) -> None:
        if self._ctx:
            self._ctx.log.debug("ExamplePlugin: plugin event — %s", data)

    # -- Dashboard Route Handler --------------------------------------------

    async def _api_status(self, request) -> dict:
        """Handler for GET /api/plugins/example/status."""
        return self.get_status()

    # -- MCP Tool Handler ---------------------------------------------------

    def _tool_hello(self, **args) -> dict:
        """Handler for the 'hello' MCP tool."""
        name = args.get("name", "World")
        prefix = "Hello"
        if self._ctx:
            prefix = self._ctx.get_config("plugins.example_plugin.greeting_prefix", "Hello")
        return {"greeting": f"{prefix}, {name}!", "plugin": self.meta.name}
