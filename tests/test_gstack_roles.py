"""gstack Role-Based Workflow Agents test suite.

Tests the gstack_roles engine: data structures, response parsing, routing,
pipeline execution, and MCP bridge tool integration. Uses mocks for LLM calls
to avoid requiring live LM Studio / Ollama backends.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_config
load_config(PROJECT_ROOT / "config.yaml", reload=True)

from engines.gstack_roles import (
    RoleResult,
    ReviewDashboard,
    GstackRole,
    ROLES,
    ROLE_ROUTING,
    ROLE_MODELS,
    ROLE_MODELS_OLLAMA,
    ROLE_TEMPERATURE,
    route_to_role,
    delegate_role,
    workflow_pipeline,
    list_roles,
    _parse_role_response,
    GSTACK_TOOLS_SCHEMA,
)


# ═══════════════════════════════════════════════════════════════════════
# Data structure tests
# ═══════════════════════════════════════════════════════════════════════

class TestRoleResult(unittest.TestCase):
    """Verify RoleResult dataclass and serialization."""

    def test_defaults(self):
        r = RoleResult(role_name="QALead", task="test task", response="ok")
        self.assertEqual(r.role_name, "QALead")
        self.assertEqual(r.task, "test task")
        self.assertEqual(r.response, "ok")
        self.assertEqual(r.actions, [])
        self.assertEqual(r.issues_found, [])
        self.assertEqual(r.confidence, 1.0)

    def test_to_dict(self):
        r = RoleResult(
            role_name="CEOReview", task="review feature",
            response="Looks great", review_grade="A+",
            actions=["Approve"], elapsed_s=1.5,
        )
        d = r.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["role_name"], "CEOReview")
        self.assertEqual(d["review_grade"], "A+")
        self.assertEqual(d["actions"], ["Approve"])
        self.assertEqual(d["elapsed_s"], 1.5)

    def test_to_dict_roundtrip(self):
        r = RoleResult(role_name="X", task="Y", response="Z", warnings=["w1"])
        d = r.to_dict()
        text = json.dumps(d)
        loaded = json.loads(text)
        self.assertEqual(loaded["warnings"], ["w1"])


class TestReviewDashboard(unittest.TestCase):
    """Verify ReviewDashboard gating logic and summary output."""

    def test_empty_dashboard_blocked(self):
        d = ReviewDashboard()
        self.assertFalse(d.is_cleared)

    def test_eng_review_clears(self):
        d = ReviewDashboard()
        d.eng_review = RoleResult(
            role_name="EngManagerReview", task="t", response="r",
            timestamp="2025-01-01T00:00:00Z",
        )
        self.assertTrue(d.is_cleared)

    def test_ceo_only_does_not_clear(self):
        d = ReviewDashboard()
        d.ceo_review = RoleResult(
            role_name="CEOReview", task="t", response="r",
            timestamp="2025-01-01T00:00:00Z",
        )
        self.assertFalse(d.is_cleared)

    def test_summary_contains_verdict(self):
        d = ReviewDashboard()
        s = d.summary()
        self.assertIn("BLOCKED", s)
        self.assertIn("Eng Review required", s)

    def test_summary_cleared(self):
        d = ReviewDashboard()
        d.eng_review = RoleResult(
            role_name="EngManagerReview", task="t", response="r",
            timestamp="2025-01-01T00:00:00Z",
        )
        s = d.summary()
        self.assertIn("CLEARED", s)
        self.assertIn("CLEAR", s)


# ═══════════════════════════════════════════════════════════════════════
# Response parsing tests
# ═══════════════════════════════════════════════════════════════════════

class TestParseRoleResponse(unittest.TestCase):
    """Verify structured field extraction from LLM responses."""

    def test_extract_actions(self):
        text = "ACTION: Refactor the router\n- ACTION: Add error handling"
        r = _parse_role_response("StaffReview", "review", text, 1.0, "test-model")
        self.assertEqual(len(r.actions), 2)
        self.assertIn("Refactor the router", r.actions[0])

    def test_extract_issues(self):
        text = "CRITICAL: Race condition in line 42\nHIGH: Missing null check"
        r = _parse_role_response("StaffReview", "review", text, 1.0, "test-model")
        self.assertEqual(len(r.issues_found), 2)

    def test_extract_auto_fixes(self):
        text = "[AUTO-FIXED] Added missing import\nAUTO-FIXED: Fixed typo"
        r = _parse_role_response("StaffReview", "review", text, 1.0, "test-model")
        self.assertEqual(len(r.auto_fixes), 2)

    def test_extract_grade(self):
        text = "GRADE: A-\nGood work overall."
        r = _parse_role_response("EngManagerReview", "review", text, 0.5, "m")
        self.assertEqual(r.review_grade, "A-")

    def test_extract_warnings(self):
        text = "WARNING: Deprecated API usage\n- WARNING: Missing docs"
        r = _parse_role_response("QALead", "qa", text, 1.0, "m")
        self.assertEqual(len(r.warnings), 2)

    def test_extract_next_steps(self):
        text = "NEXT: Write integration tests\nNEXT STEP: Deploy to staging"
        r = _parse_role_response("ReleaseEngineer", "ship", text, 1.0, "m")
        self.assertEqual(len(r.next_steps), 2)

    def test_extract_test_plan(self):
        text = "TEST: Verify login flow\n- TEST: Check error states"
        r = _parse_role_response("QALead", "qa", text, 1.0, "m")
        self.assertEqual(len(r.test_plan), 2)

    def test_extract_diagrams(self):
        text = "Here is the arch:\n```\n[A] --> [B]\n[B] --> [C]\n```\nEnd."
        r = _parse_role_response("EngManagerReview", "design", text, 1.0, "m")
        self.assertEqual(len(r.diagrams), 1)
        self.assertIn("[A] --> [B]", r.diagrams[0])

    def test_empty_response(self):
        r = _parse_role_response("DocWriter", "doc", "", 0.1, "m")
        self.assertEqual(r.actions, [])
        self.assertEqual(r.issues_found, [])
        self.assertEqual(r.response, "")

    def test_metadata_preserved(self):
        r = _parse_role_response("CEOReview", "plan", "text", 2.5, "qwen3")
        self.assertEqual(r.role_name, "CEOReview")
        self.assertEqual(r.task, "plan")
        self.assertEqual(r.elapsed_s, 2.5)
        self.assertEqual(r.model_used, "qwen3")


# ═══════════════════════════════════════════════════════════════════════
# Role registry tests
# ═══════════════════════════════════════════════════════════════════════

class TestRoleRegistry(unittest.TestCase):
    """Verify role creation, configuration, and registry integrity."""

    def test_all_seven_roles_exist(self):
        expected = {"CEOReview", "EngManagerReview", "StaffReview", "QALead",
                    "ReleaseEngineer", "RetroAnalyst", "DocWriter"}
        self.assertEqual(set(ROLES.keys()), expected)

    def test_roles_have_system_prompts(self):
        for name, role in ROLES.items():
            self.assertTrue(len(role.system_prompt) > 0,
                            f"Role {name} has empty system prompt")

    def test_roles_have_slash_commands(self):
        for name, role in ROLES.items():
            self.assertTrue(role.slash_command.startswith("/"),
                            f"Role {name} slash_command should start with /")

    def test_role_to_dict(self):
        role = ROLES["CEOReview"]
        d = role.to_dict()
        self.assertEqual(d["name"], "CEOReview")
        self.assertIn("role", d)
        self.assertIn("slash_command", d)
        self.assertIn("tools", d)

    def test_model_assignments_cover_all_roles(self):
        for name in ROLES:
            self.assertIn(name, ROLE_MODELS, f"Missing LM Studio model for {name}")
            self.assertIn(name, ROLE_MODELS_OLLAMA, f"Missing Ollama model for {name}")
            self.assertIn(name, ROLE_TEMPERATURE, f"Missing temperature for {name}")

    def test_temperatures_valid_range(self):
        for name, temp in ROLE_TEMPERATURE.items():
            self.assertGreaterEqual(temp, 0.0)
            self.assertLessEqual(temp, 2.0)


# ═══════════════════════════════════════════════════════════════════════
# Routing tests
# ═══════════════════════════════════════════════════════════════════════

class TestRouting(unittest.TestCase):
    """Verify keyword-based routing selects the correct role."""

    def test_route_product_to_ceo(self):
        role = route_to_role("We need a product roadmap for the new feature")
        self.assertEqual(role.name, "CEOReview")

    def test_route_architecture_to_eng(self):
        role = route_to_role("Design the architecture for the data flow pipeline")
        self.assertEqual(role.name, "EngManagerReview")

    def test_route_bug_to_staff(self):
        role = route_to_role("Fix this race condition bug in the handler")
        self.assertEqual(role.name, "StaffReview")

    def test_route_qa_to_qa(self):
        role = route_to_role("Test the dashboard UI for responsive layout")
        self.assertEqual(role.name, "QALead")

    def test_route_ship_to_release(self):
        role = route_to_role("Ship the release and check coverage before deploy")
        self.assertEqual(role.name, "ReleaseEngineer")

    def test_route_retro_to_analyst(self):
        role = route_to_role("Run the weekly retro and check velocity metrics")
        self.assertEqual(role.name, "RetroAnalyst")

    def test_route_doc_to_writer(self):
        role = route_to_role("Update the README documentation for the changelog")
        self.assertEqual(role.name, "DocWriter")

    def test_unknown_defaults_to_eng(self):
        role = route_to_role("xyzzy foobar nonsense input")
        self.assertEqual(role.name, "EngManagerReview")

    def test_routing_keywords_cover_all_roles(self):
        for role_name in ROLES:
            self.assertIn(role_name, ROLE_ROUTING,
                          f"Missing routing keywords for {role_name}")


# ═══════════════════════════════════════════════════════════════════════
# Public API tests (mocked LLM calls)
# ═══════════════════════════════════════════════════════════════════════

MOCK_LLM_RESPONSE = (
    "GRADE: A\n"
    "ACTION: Approve the change\n"
    "WARNING: Check edge cases\n"
    "NEXT: Write integration tests\n"
    "TEST: Verify error handling path\n"
)


def _mock_lmstudio_success(messages, model, temperature=0.3, max_tokens=2048):
    return MOCK_LLM_RESPONSE, model


def _mock_lmstudio_fail(messages, model, temperature=0.3, max_tokens=2048):
    return "", ""


def _mock_ollama_success(messages, model, temperature=0.3):
    return MOCK_LLM_RESPONSE, model


class TestDelegateRole(unittest.TestCase):
    """Test delegate_role with mocked LLM backends."""

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_delegate_auto_route(self, mock_lm):
        result = delegate_role("Review this code for bugs and race conditions")
        self.assertIsInstance(result, RoleResult)
        self.assertEqual(result.role_name, "StaffReview")
        self.assertIn("Approve the change", result.actions)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_delegate_explicit_role(self, mock_lm):
        result = delegate_role("Check the docs", role_name="DocWriter")
        self.assertEqual(result.role_name, "DocWriter")

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_delegate_with_scope_mode(self, mock_lm):
        result = delegate_role("Rethink the product", role_name="CEOReview", scope_mode="expansion")
        self.assertEqual(result.scope_mode, "expansion")

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_fail)
    @patch("engines.gstack_roles._call_ollama", side_effect=_mock_ollama_success)
    def test_fallback_to_ollama(self, mock_ollama, mock_lm):
        result = delegate_role("Ship the release", role_name="ReleaseEngineer")
        self.assertIsInstance(result, RoleResult)
        mock_ollama.assert_called_once()

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_fail)
    @patch("engines.gstack_roles._call_ollama", side_effect=lambda *a, **k: ("", ""))
    def test_no_llm_available(self, mock_ollama, mock_lm):
        result = delegate_role("Do something", role_name="EngManagerReview")
        self.assertIn("ERROR", result.response)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_delegate_invalid_role_falls_back(self, mock_lm):
        result = delegate_role("something", role_name="NonExistentRole")
        self.assertEqual(result.role_name, "EngManagerReview")

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_result_has_timestamp(self, mock_lm):
        result = delegate_role("plan", role_name="CEOReview")
        self.assertTrue(len(result.timestamp) > 0)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_result_serializable(self, mock_lm):
        result = delegate_role("test", role_name="QALead")
        d = result.to_dict()
        text = json.dumps(d, default=str)
        self.assertIsInstance(text, str)


class TestWorkflowPipeline(unittest.TestCase):
    """Test the multi-role pipeline with mocked LLM calls."""

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_full_pipeline(self, mock_lm):
        results, dashboard = workflow_pipeline("Implement feature X")
        self.assertEqual(len(results), 4)  # CEO + Eng + Staff + QA
        self.assertTrue(dashboard.is_cleared)
        self.assertIsNotNone(dashboard.ceo_review)
        self.assertIsNotNone(dashboard.eng_review)
        self.assertIsNotNone(dashboard.staff_review)
        self.assertIsNotNone(dashboard.qa_review)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_pipeline_skip_ceo(self, mock_lm):
        results, dashboard = workflow_pipeline("Feature Y", skip_ceo=True)
        self.assertEqual(len(results), 3)  # Eng + Staff + QA
        self.assertIsNone(dashboard.ceo_review)
        self.assertTrue(dashboard.is_cleared)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_pipeline_skip_qa(self, mock_lm):
        results, dashboard = workflow_pipeline("Feature Z", skip_qa=True)
        self.assertEqual(len(results), 3)  # CEO + Eng + Staff
        self.assertIsNone(dashboard.qa_review)
        self.assertTrue(dashboard.is_cleared)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_pipeline_skip_both(self, mock_lm):
        results, dashboard = workflow_pipeline("Feature W", skip_ceo=True, skip_qa=True)
        self.assertEqual(len(results), 2)  # Eng + Staff only
        self.assertTrue(dashboard.is_cleared)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_pipeline_dashboard_summary_string(self, mock_lm):
        _, dashboard = workflow_pipeline("Task")
        summary = dashboard.summary()
        self.assertIsInstance(summary, str)
        self.assertIn("REVIEW READINESS DASHBOARD", summary)


# ═══════════════════════════════════════════════════════════════════════
# list_roles tests
# ═══════════════════════════════════════════════════════════════════════

class TestListRoles(unittest.TestCase):
    """Test the list_roles public API."""

    def test_returns_dict(self):
        roles = list_roles()
        self.assertIsInstance(roles, dict)

    def test_all_roles_present(self):
        roles = list_roles()
        expected = {"CEOReview", "EngManagerReview", "StaffReview", "QALead",
                    "ReleaseEngineer", "RetroAnalyst", "DocWriter"}
        self.assertEqual(set(roles.keys()), expected)

    def test_role_entries_have_fields(self):
        roles = list_roles()
        for name, info in roles.items():
            self.assertIn("name", info)
            self.assertIn("role", info)
            self.assertIn("slash_command", info)

    def test_serializable(self):
        roles = list_roles()
        text = json.dumps(roles)
        self.assertIsInstance(text, str)


# ═══════════════════════════════════════════════════════════════════════
# MCP bridge integration tests
# ═══════════════════════════════════════════════════════════════════════

class TestGstackMCPBridge(unittest.TestCase):
    """Test gstack tools are registered in the main MCP bridge."""

    def test_gstack_tools_in_bridge(self):
        from mcp_bridge import TOOLS
        tool_names = {t["name"] for t in TOOLS}
        self.assertIn("gstack_delegate", tool_names)
        self.assertIn("gstack_pipeline", tool_names)
        self.assertIn("gstack_list_roles", tool_names)

    def test_gstack_tools_have_handlers(self):
        from mcp_bridge import TOOLS
        gstack_tools = [t for t in TOOLS if t["name"].startswith("gstack_")]
        self.assertEqual(len(gstack_tools), 3)
        for t in gstack_tools:
            self.assertTrue(callable(t["handler"]),
                            f"gstack tool '{t['name']}' handler not callable")

    def test_gstack_delegate_schema(self):
        from mcp_bridge import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "gstack_delegate")
        schema = tool["inputSchema"]
        self.assertIn("task", schema["properties"])
        self.assertIn("task", schema["required"])

    def test_gstack_pipeline_schema(self):
        from mcp_bridge import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "gstack_pipeline")
        schema = tool["inputSchema"]
        self.assertIn("task", schema["properties"])
        self.assertIn("skip_ceo", schema["properties"])
        self.assertIn("skip_qa", schema["properties"])

    def test_gstack_list_roles_schema(self):
        from mcp_bridge import TOOLS
        tool = next(t for t in TOOLS if t["name"] == "gstack_list_roles")
        schema = tool["inputSchema"]
        self.assertEqual(schema["type"], "object")

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_bridge_handle_gstack_delegate(self, mock_lm):
        from mcp_bridge import handle_request
        resp = handle_request({
            "method": "tools/call", "id": 100,
            "params": {"name": "gstack_delegate", "arguments": {"task": "Review code for bugs"}},
        })
        self.assertEqual(resp["id"], 100)
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("role_name", data)

    @patch("engines.gstack_roles._call_lmstudio", side_effect=_mock_lmstudio_success)
    def test_bridge_handle_gstack_list_roles(self, mock_lm):
        from mcp_bridge import handle_request
        resp = handle_request({
            "method": "tools/call", "id": 101,
            "params": {"name": "gstack_list_roles", "arguments": {}},
        })
        self.assertFalse(resp["result"]["isError"])
        data = json.loads(resp["result"]["content"][0]["text"])
        self.assertIn("roles", data)
        self.assertEqual(data["count"], 7)


# ═══════════════════════════════════════════════════════════════════════
# gstack standalone MCP tool schema tests
# ═══════════════════════════════════════════════════════════════════════

class TestGstackToolSchema(unittest.TestCase):
    """Verify the standalone GSTACK_TOOLS_SCHEMA in gstack_roles.py."""

    def test_three_tools_defined(self):
        self.assertEqual(len(GSTACK_TOOLS_SCHEMA), 3)

    def test_tool_names(self):
        names = {t["name"] for t in GSTACK_TOOLS_SCHEMA}
        self.assertEqual(names, {"gstack_delegate", "gstack_pipeline", "gstack_list_roles"})

    def test_schemas_valid(self):
        for tool in GSTACK_TOOLS_SCHEMA:
            self.assertIn("inputSchema", tool)
            self.assertEqual(tool["inputSchema"]["type"], "object")
            self.assertIn("properties", tool["inputSchema"])


if __name__ == "__main__":
    unittest.main()
