"""MCP Bridge test suite — tool dispatch, error handling, JSON-RPC protocol.

Tests the MCP server's handle_request function and tool registry without
requiring live engine backends (uses mocks for heavy engine calls).
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

from mcp_bridge import handle_request, TOOLS


# ═══════════════════════════════════════════════════════════════════════
# Protocol tests
# ═══════════════════════════════════════════════════════════════════════

class TestMCPProtocol(unittest.TestCase):
    """Test MCP JSON-RPC protocol handling."""

    def test_initialize(self):
        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        self.assertEqual(resp["jsonrpc"], "2.0")
        self.assertEqual(resp["id"], 1)
        result = resp["result"]
        self.assertIn("protocolVersion", result)
        self.assertIn("capabilities", result)
        self.assertIn("serverInfo", result)
        self.assertEqual(result["serverInfo"]["name"], "hyperspin-toolkit")

    def test_initialized_notification(self):
        resp = handle_request({"method": "notifications/initialized", "id": None})
        self.assertIsNone(resp)

    def test_ping(self):
        resp = handle_request({"method": "ping", "id": 42})
        self.assertEqual(resp["id"], 42)
        self.assertEqual(resp["result"], {})

    def test_unknown_method(self):
        resp = handle_request({"method": "nonexistent/method", "id": 99})
        self.assertIn("error", resp)
        self.assertEqual(resp["error"]["code"], -32601)

    def test_tools_list(self):
        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        self.assertEqual(resp["id"], 2)
        tools = resp["result"]["tools"]
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 10)
        # Each tool should have name, description, inputSchema
        for t in tools:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("inputSchema", t)


# ═══════════════════════════════════════════════════════════════════════
# Tool registry integrity
# ═══════════════════════════════════════════════════════════════════════

class TestToolRegistry(unittest.TestCase):
    """Verify tool definitions are well-formed."""

    def test_all_tools_have_handler(self):
        for tool in TOOLS:
            self.assertTrue(callable(tool["handler"]),
                            f"Tool '{tool['name']}' handler is not callable")

    def test_unique_names(self):
        names = [t["name"] for t in TOOLS]
        self.assertEqual(len(names), len(set(names)), "Duplicate tool names found")

    def test_all_tools_have_description(self):
        for tool in TOOLS:
            self.assertIsInstance(tool["description"], str)
            self.assertGreater(len(tool["description"]), 10,
                               f"Tool '{tool['name']}' description too short")

    def test_input_schema_format(self):
        for tool in TOOLS:
            schema = tool["inputSchema"]
            self.assertIsInstance(schema, dict)
            self.assertEqual(schema.get("type"), "object")
            self.assertIn("properties", schema)

    def test_known_tools_exist(self):
        names = {t["name"] for t in TOOLS}
        expected = [
            "audit_full", "audit_system", "get_stats",
            "find_duplicates", "optimize_report",
            "plugin_list", "plugin_enable", "plugin_disable",
            "drives_scan", "drives_status",
        ]
        for name in expected:
            self.assertIn(name, names, f"Expected tool '{name}' not found")


# ═══════════════════════════════════════════════════════════════════════
# Tool dispatch tests
# ═══════════════════════════════════════════════════════════════════════

class TestToolDispatch(unittest.TestCase):
    """Test tools/call dispatch and error handling."""

    def test_call_unknown_tool(self):
        resp = handle_request({
            "method": "tools/call",
            "id": 10,
            "params": {"name": "nonexistent_tool", "arguments": {}},
        })
        self.assertTrue(resp["result"]["isError"])
        self.assertIn("Unknown tool", resp["result"]["content"][0]["text"])

    @patch("core.database.execute")
    def test_call_get_stats(self, mock_db):
        mock_db.side_effect = [
            [{"cnt": 184}],   # systems count
            [{"cnt": 50000}], # rom count
            [{"cnt": 173}],   # emulator count
            [{"cnt": 150}],   # healthy emulators
            [{"cnt": 5}],     # backups
        ]
        resp = handle_request({
            "method": "tools/call",
            "id": 11,
            "params": {"name": "get_stats", "arguments": {}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["systems"], 184)

    @patch("engines.auditor.audit_system")
    def test_call_audit_system_with_args(self, mock_audit):
        mock_audit.return_value = {
            "name": "MAME",
            "rom_count": 5000,
            "health_score": 85.0,
        }
        resp = handle_request({
            "method": "tools/call",
            "id": 12,
            "params": {"name": "audit_system", "arguments": {"system_name": "MAME"}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertEqual(data["name"], "MAME")
        mock_audit.assert_called_once_with("MAME")

    def test_call_plugin_list(self):
        resp = handle_request({
            "method": "tools/call",
            "id": 13,
            "params": {"name": "plugin_list", "arguments": {}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("plugins", data)
        self.assertIn("total", data)

    def test_call_tool_handler_exception(self):
        """When a tool handler raises, MCP should return isError=True."""
        # Temporarily add a broken tool
        broken = {
            "name": "_test_broken",
            "description": "test",
            "inputSchema": {"type": "object", "properties": {}},
            "handler": lambda **kw: 1 / 0,
        }
        TOOLS.append(broken)
        try:
            resp = handle_request({
                "method": "tools/call",
                "id": 14,
                "params": {"name": "_test_broken", "arguments": {}},
            })
            self.assertTrue(resp["result"]["isError"])
            self.assertIn("ZeroDivisionError", resp["result"]["content"][0]["text"])
        finally:
            TOOLS.remove(broken)

    @patch("engines.space_optimizer.find_duplicate_roms")
    def test_call_find_duplicates_optional_args(self, mock_dup):
        mock_dup.return_value = {
            "duplicates": [],
            "total_wasted": 0,
            "file_count": 0,
            "duplicate_groups": 0,
        }
        resp = handle_request({
            "method": "tools/call",
            "id": 15,
            "params": {"name": "find_duplicates", "arguments": {"directory": "D:\\test"}},
        })
        self.assertFalse(resp["result"]["isError"])
        mock_dup.assert_called_once_with(rom_dirs=["D:\\test"])


# ═══════════════════════════════════════════════════════════════════════
# Plugin tool dispatch
# ═══════════════════════════════════════════════════════════════════════

class TestPluginToolDispatch(unittest.TestCase):
    """Test plugin-related MCP tool handlers."""

    def test_plugin_enable_dispatch(self):
        resp = handle_request({
            "method": "tools/call",
            "id": 20,
            "params": {"name": "plugin_enable", "arguments": {"name": "example_plugin"}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("enabled", data)

    def test_plugin_call_tool_not_found(self):
        resp = handle_request({
            "method": "tools/call",
            "id": 21,
            "params": {"name": "plugin_call_tool", "arguments": {"tool_name": "nonexistent"}},
        })
        self.assertFalse(resp["result"]["isError"])  # MCP doesn't error, tool returns error dict
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("error", data)

    def test_plugin_events(self):
        resp = handle_request({
            "method": "tools/call",
            "id": 22,
            "params": {"name": "plugin_events", "arguments": {}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("events", data)
        self.assertIn("total_events", data)


# ═══════════════════════════════════════════════════════════════════════
# Response format validation
# ═══════════════════════════════════════════════════════════════════════

class TestResponseFormat(unittest.TestCase):
    """Ensure all responses conform to JSON-RPC 2.0 format."""

    def test_initialize_has_jsonrpc(self):
        resp = handle_request({"method": "initialize", "id": 1, "params": {}})
        self.assertEqual(resp["jsonrpc"], "2.0")

    def test_tools_list_has_jsonrpc(self):
        resp = handle_request({"method": "tools/list", "id": 2, "params": {}})
        self.assertEqual(resp["jsonrpc"], "2.0")

    def test_error_has_jsonrpc(self):
        resp = handle_request({"method": "invalid", "id": 3})
        self.assertEqual(resp["jsonrpc"], "2.0")

    def test_id_preserved(self):
        for req_id in [1, 42, "abc", None]:
            resp = handle_request({"method": "ping", "id": req_id})
            self.assertEqual(resp["id"], req_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
