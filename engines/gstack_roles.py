"""gstack Role-Based Workflow Agents — Adapted from garrytan/gstack.

Implements gstack's role-based cognitive modes for the HyperSpin Extreme Toolkit,
powered entirely by local LLMs (LM Studio / Ollama). Zero cloud dependency.

gstack gives agents workflow-stage specialisation (Plan -> Build -> Review -> QA -> Ship)
which is orthogonal to NemoClaw's task specialisation (ROM, Emulator, Media, etc.).
Combined, they form a 2-axis agent matrix:

    NemoClaw (WHAT):  ROM | Emulator | Media | Database | Space | Update
    gstack   (HOW):   CEO | EngMgr   | Review | QA      | Ship  | Retro | DocWriter

Reference: https://github.com/garrytan/gstack (MIT License, Garry Tan / YC)

Roles:
  - CEOReview        Product-level rethinking, 10-star product vision, scope modes
  - EngManagerReview Architecture validation, diagrams, edge cases, test matrices
  - StaffReview      Bug hunting, auto-fix, completeness audit, race conditions
  - QALead           Headless browser testing, regression test generation
  - ReleaseEngineer  Test runner, coverage audit, PR generation, ship pipeline
  - RetroAnalyst     Weekly retro, shipping velocity, test health, team metrics
  - DocWriter        Auto-update docs to match code changes, catch stale READMEs
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

from core.logger import get_logger

log = get_logger("gstack_roles")

# ── Local inference endpoints (shared with nemoclaw_agents) ──────────
LMSTUDIO_URL = "http://localhost:1234/v1/chat/completions"
LMSTUDIO_KEY = "lm-studio"
OLLAMA_URL = "http://localhost:11434/api/chat"

# Model assignments per role
ROLE_MODELS = {
    "CEOReview":        "eugenehp/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_S.gguf",
    "EngManagerReview": "eugenehp/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_S.gguf",
    "StaffReview":      "eugenehp/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-GGUF/Qwen3.5-27B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_S.gguf",
    "QALead":           "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
    "ReleaseEngineer":  "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
    "RetroAnalyst":     "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
    "DocWriter":        "kryp1234/Qwen3.5-9B-Claude-4.6-OS-Auto-Variable-HERETIC-UNCENSORED-THINKING-MAX-NEOCODE-Imatrix-GGUF/Qwen3.5-9B-Claude-4.6-OS-AV-H-UNCENSORED-THINK-D_AU-Q8_0.gguf",
}

ROLE_MODELS_OLLAMA = {
    "CEOReview": "qwen3:14b", "EngManagerReview": "qwen3:14b",
    "StaffReview": "qwen3:14b", "QALead": "qwen3:8b",
    "ReleaseEngineer": "qwen3:8b", "RetroAnalyst": "qwen3:8b",
    "DocWriter": "qwen3:8b",
}

ROLE_TEMPERATURE = {
    "CEOReview": 0.7, "EngManagerReview": 0.1, "StaffReview": 0.1,
    "QALead": 0.2, "ReleaseEngineer": 0.1, "RetroAnalyst": 0.4,
    "DocWriter": 0.3,
}


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class RoleResult:
    """Structured output from a gstack role agent."""
    role_name: str
    task: str
    response: str
    scope_mode: str = ""
    review_grade: str = ""
    actions: list[str] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)
    issues_found: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    diagrams: list[str] = field(default_factory=list)
    test_plan: list[str] = field(default_factory=list)
    confidence: float = 1.0
    elapsed_s: float = 0.0
    model_used: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewDashboard:
    """Review Readiness Dashboard -- tracks which reviews have run."""
    ceo_review: Optional[RoleResult] = None
    eng_review: Optional[RoleResult] = None
    staff_review: Optional[RoleResult] = None
    qa_review: Optional[RoleResult] = None
    doc_review: Optional[RoleResult] = None

    @property
    def is_cleared(self) -> bool:
        """Eng review is the only required gate (gstack convention)."""
        return self.eng_review is not None

    def summary(self) -> str:
        lines = [
            "+====================================================================+",
            "|                    REVIEW READINESS DASHBOARD                       |",
            "+====================================================================+",
            "| Review          | Runs | Last Run            | Status    | Required |",
            "|-----------------|------|---------------------|-----------|----------|",
        ]
        for name, result, required in [
            ("CEO Review", self.ceo_review, False),
            ("Eng Review", self.eng_review, True),
            ("Staff Review", self.staff_review, False),
            ("QA Review", self.qa_review, False),
            ("Doc Review", self.doc_review, False),
        ]:
            if result:
                status = "CLEAR"
                run_time = result.timestamp[:19] if result.timestamp else "-"
                runs = "1"
            else:
                status = "-"
                run_time = "-"
                runs = "0"
            req = "YES" if required else "no"
            lines.append(
                f"| {name:<15} |  {runs}   | {run_time:<19} | {status:<9} | {req:<8} |"
            )
        verdict = "CLEARED" if self.is_cleared else "BLOCKED -- Eng Review required"
        lines.append("+--------------------------------------------------------------------+")
        lines.append(f"| VERDICT: {verdict:<55} |")
        lines.append("+====================================================================+")
        return "\n".join(lines)


# ── LLM calls ────────────────────────────────────────────────────────

def _call_lmstudio(
    messages: list[dict], model: str, temperature: float = 0.3, max_tokens: int = 2048,
) -> tuple[str, str]:
    if not _HAS_HTTPX:
        return "", ""
    try:
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        r = httpx.post(
            LMSTUDIO_URL,
            headers={"Authorization": f"Bearer {LMSTUDIO_KEY}"},
            json=payload,
            timeout=180.0,
        )
        if r.status_code == 200:
            data = r.json()
            text = data["choices"][0]["message"]["content"]
            used = data.get("model", model)
            return text, used
    except Exception as exc:
        log.debug("LM Studio call failed: %s", exc)
    return "", ""


def _call_ollama(
    messages: list[dict], model: str, temperature: float = 0.3,
) -> tuple[str, str]:
    if not _HAS_HTTPX:
        return "", ""
    try:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }
        r = httpx.post(OLLAMA_URL, json=payload, timeout=180.0)
        if r.status_code == 200:
            text = r.json()["message"]["content"]
            return text, model
    except Exception as exc:
        log.debug("Ollama call failed: %s", exc)
    return "", ""


def _parse_role_response(
    role_name: str, task: str, text: str, elapsed: float, model: str,
) -> RoleResult:
    """Extract structured data from role agent response."""
    actions, auto_fixes, issues, warnings, next_steps = [], [], [], [], []
    diagrams, test_plan = [], []
    grade = ""
    in_diagram = False
    diagram_buf: list[str] = []

    for line in text.splitlines():
        s = line.strip()

        # Diagram capture (ASCII art between ``` blocks or lines with box chars)
        if s.startswith("```"):
            if in_diagram:
                diagrams.append("\n".join(diagram_buf))
                diagram_buf = []
            in_diagram = not in_diagram
            continue
        if in_diagram:
            diagram_buf.append(line)
            continue

        # Structured field extraction
        if s.startswith(("ACTION:", "- ACTION:")):
            actions.append(s.split(":", 1)[1].strip())
        elif s.startswith(("AUTO-FIXED:", "- AUTO-FIXED:", "[AUTO-FIXED]")):
            auto_fixes.append(s.split("]", 1)[-1].split(":", 1)[-1].strip())
        elif s.startswith(("CRITICAL:", "HIGH:", "MEDIUM:", "LOW:", "- CRITICAL:", "- HIGH:")):
            issues.append(s)
        elif s.startswith(("WARNING:", "- WARNING:")):
            warnings.append(s.split(":", 1)[1].strip())
        elif s.startswith(("NEXT:", "- NEXT:", "NEXT STEP:")):
            next_steps.append(s.split(":", 1)[1].strip())
        elif s.startswith(("TEST:", "- TEST:", "TEST CASE:")):
            test_plan.append(s.split(":", 1)[1].strip())
        elif s.startswith("GRADE:"):
            grade = s.split(":", 1)[1].strip()[:2]

    if in_diagram and diagram_buf:
        diagrams.append("\n".join(diagram_buf))

    return RoleResult(
        role_name=role_name, task=task, response=text,
        review_grade=grade, actions=actions, auto_fixes=auto_fixes,
        issues_found=issues, warnings=warnings, next_steps=next_steps,
        diagrams=diagrams, test_plan=test_plan,
        elapsed_s=elapsed, model_used=model,
    )


# ── Role system prompts ──────────────────────────────────────────────

_PROMPTS = {}  # populated by _load_prompts()


def _load_prompts() -> dict[str, str]:
    """Load role prompts from skills/ SKILL.md files, falling back to built-in."""
    global _PROMPTS
    if _PROMPTS:
        return _PROMPTS

    skills_dir = Path(__file__).resolve().parent.parent / "skills"
    for role_name, filename in [
        ("CEOReview", "ceo-review"), ("EngManagerReview", "eng-review"),
        ("StaffReview", "staff-review"), ("QALead", "qa-lead"),
        ("ReleaseEngineer", "release-engineer"), ("RetroAnalyst", "retro-analyst"),
        ("DocWriter", "doc-writer"),
    ]:
        skill_path = skills_dir / filename / "SKILL.md"
        if skill_path.exists():
            _PROMPTS[role_name] = skill_path.read_text(encoding="utf-8")
        else:
            _PROMPTS[role_name] = _BUILTIN_PROMPTS.get(role_name, "")

    return _PROMPTS


# Built-in prompts (used when SKILL.md files don't exist yet)
_BUILTIN_PROMPTS: dict[str, str] = {}  # populated below after role definitions


# ── Role Agent class ─────────────────────────────────────────────────

@dataclass
class GstackRole:
    """A gstack workflow role agent that uses local LLMs for reasoning."""
    name: str
    role: str
    system_prompt: str
    slash_command: str
    tools: list[str] = field(default_factory=list)

    def invoke(self, task: str, context: str = "", scope_mode: str = "") -> RoleResult:
        """Invoke this role agent with a task and optional context."""
        start = time.time()
        messages = [{"role": "system", "content": self.system_prompt}]

        user_msg = ""
        if scope_mode and self.name == "CEOReview":
            user_msg += f"[SCOPE MODE: {scope_mode.upper()}]\n\n"
        if context:
            user_msg += f"Context data:\n{context}\n\n"
        user_msg += f"Task: {task}"
        messages.append({"role": "user", "content": user_msg})

        model = ROLE_MODELS.get(self.name, "auto")
        temp = ROLE_TEMPERATURE.get(self.name, 0.3)
        max_tok = 4096 if self.name in ("CEOReview", "EngManagerReview", "StaffReview") else 2048

        response_text, model_used = _call_lmstudio(messages, model, temp, max_tok)
        if not response_text:
            model_ollama = ROLE_MODELS_OLLAMA.get(self.name, "qwen3:14b")
            response_text, model_used = _call_ollama(messages, model_ollama, temp)
        if not response_text:
            response_text = "ERROR: No LLM provider available. Start LM Studio or Ollama."

        elapsed = round(time.time() - start, 2)
        result = _parse_role_response(self.name, task, response_text, elapsed, model_used)
        result.scope_mode = scope_mode
        result.timestamp = datetime.now(timezone.utc).isoformat()

        log.info("gstack/%s completed in %.2fs (model=%s)", self.name, elapsed, model_used)
        return result

    def to_dict(self) -> dict:
        return {"name": self.name, "role": self.role, "slash_command": self.slash_command, "tools": self.tools}


# ── Role Registry ────────────────────────────────────────────────────

def create_roles() -> dict[str, GstackRole]:
    prompts = _load_prompts()
    return {
        "CEOReview": GstackRole(
            name="CEOReview",
            role="Product visionary -- rethink the problem, find the 10-star product",
            system_prompt=prompts.get("CEOReview", "You are a product visionary."),
            slash_command="/plan-ceo-review",
            tools=["audit_full", "get_stats"],
        ),
        "EngManagerReview": GstackRole(
            name="EngManagerReview",
            role="Technical architect -- lock architecture, diagrams, edge cases, tests",
            system_prompt=prompts.get("EngManagerReview", "You are a technical architect."),
            slash_command="/plan-eng-review",
            tools=["audit_full", "get_stats", "list_engines"],
        ),
        "StaffReview": GstackRole(
            name="StaffReview",
            role="Staff engineer -- paranoid code review, auto-fix, completeness audit",
            system_prompt=prompts.get("StaffReview", "You are a code reviewer."),
            slash_command="/review",
            tools=["audit_full", "self_heal_scan", "self_heal_fix"],
        ),
        "QALead": GstackRole(
            name="QALead",
            role="QA lead -- test app, find bugs, fix them, generate regression tests",
            system_prompt=prompts.get("QALead", "You are a QA lead."),
            slash_command="/qa",
            tools=["browse_snapshot", "browse_click", "browse_screenshot"],
        ),
        "ReleaseEngineer": GstackRole(
            name="ReleaseEngineer",
            role="Release engineer -- run tests, audit coverage, ship PRs",
            system_prompt=prompts.get("ReleaseEngineer", "You are a release engineer."),
            slash_command="/ship",
            tools=["run_tests", "audit_coverage", "git_status"],
        ),
        "RetroAnalyst": GstackRole(
            name="RetroAnalyst",
            role="Retro analyst -- weekly metrics, velocity, test health, team stats",
            system_prompt=prompts.get("RetroAnalyst", "You are an engineering manager."),
            slash_command="/retro",
            tools=["git_log", "get_stats"],
        ),
        "DocWriter": GstackRole(
            name="DocWriter",
            role="Technical writer -- auto-update docs, catch stale READMEs",
            system_prompt=prompts.get("DocWriter", "You are a technical writer."),
            slash_command="/document-release",
            tools=["list_docs", "read_doc", "write_doc"],
        ),
    }


ROLES = create_roles()


# ── Routing ──────────────────────────────────────────────────────────

ROLE_ROUTING: dict[str, list[str]] = {
    "CEOReview":        ["product", "vision", "feature", "roadmap", "scope", "10-star", "rethink", "ceo"],
    "EngManagerReview": ["architecture", "design", "diagram", "data flow", "edge case", "test matrix", "eng review"],
    "StaffReview":      ["review", "bug", "code review", "race condition", "fix", "lint", "refactor"],
    "QALead":           ["qa", "test", "browser", "dashboard", "ui", "click", "form", "responsive"],
    "ReleaseEngineer":  ["ship", "release", "deploy", "pr", "coverage", "pytest", "ci"],
    "RetroAnalyst":     ["retro", "velocity", "metrics", "commits", "weekly", "stats"],
    "DocWriter":        ["doc", "readme", "changelog", "milestone", "todo", "documentation", "stale"],
}


def route_to_role(task: str) -> GstackRole:
    """Select the best gstack role for a task based on keywords."""
    task_lower = task.lower()
    scores: dict[str, int] = {name: 0 for name in ROLES}
    for role_name, keywords in ROLE_ROUTING.items():
        for kw in keywords:
            if kw in task_lower:
                scores[role_name] += len(kw)
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        best = "EngManagerReview"  # default
    return ROLES[best]


# ── Public API ───────────────────────────────────────────────────────

def delegate_role(
    task: str, context: str = "", role_name: Optional[str] = None, scope_mode: str = "",
) -> RoleResult:
    """Route a task to the best gstack role and return its result."""
    role = ROLES.get(role_name) if role_name else route_to_role(task)
    if role is None:
        role = ROLES["EngManagerReview"]
    return role.invoke(task, context, scope_mode)


def workflow_pipeline(
    task: str, context: str = "", skip_ceo: bool = False, skip_qa: bool = False,
) -> tuple[list[RoleResult], ReviewDashboard]:
    """Run the full gstack workflow pipeline: CEO -> Eng -> Review -> QA -> Ship."""
    results: list[RoleResult] = []
    dashboard = ReviewDashboard()

    # 1. CEO Review (optional)
    if not skip_ceo:
        ceo = ROLES["CEOReview"].invoke(task, context, scope_mode="selective_expansion")
        results.append(ceo)
        dashboard.ceo_review = ceo
        context = f"CEO Vision:\n{ceo.response}\n\nOriginal context:\n{context}"

    # 2. Eng Manager Review (required gate)
    eng = ROLES["EngManagerReview"].invoke(task, context)
    results.append(eng)
    dashboard.eng_review = eng
    context = f"Eng Architecture:\n{eng.response}\n\n{context}"

    # 3. Staff Review
    staff = ROLES["StaffReview"].invoke(task, context)
    results.append(staff)
    dashboard.staff_review = staff

    # 4. QA (optional)
    if not skip_qa:
        qa = ROLES["QALead"].invoke(task, context)
        results.append(qa)
        dashboard.qa_review = qa

    log.info("gstack pipeline complete: %d reviews, cleared=%s", len(results), dashboard.is_cleared)
    return results, dashboard


def list_roles() -> dict[str, dict]:
    """List all available gstack roles."""
    return {name: role.to_dict() for name, role in ROLES.items()}


# ── MCP stdio interface for Goose ────────────────────────────────────

GSTACK_TOOLS_SCHEMA = [
    {
        "name": "gstack_delegate",
        "description": "Route a task to the best gstack workflow role (CEO, Eng Manager, Staff Review, QA, Ship, Retro, DocWriter). Uses local LLM for reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Task description"},
                "context": {"type": "string", "description": "Optional context data"},
                "role_name": {"type": "string", "description": "Force a specific role: CEOReview, EngManagerReview, StaffReview, QALead, ReleaseEngineer, RetroAnalyst, DocWriter"},
                "scope_mode": {"type": "string", "description": "CEO scope mode: expansion, selective_expansion, hold, reduction"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "gstack_pipeline",
        "description": "Run the full gstack review pipeline (CEO -> Eng -> Review -> QA) and return results with Review Readiness Dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Feature or task to review"},
                "context": {"type": "string", "description": "Optional context data"},
                "skip_ceo": {"type": "boolean", "description": "Skip CEO review (default false)"},
                "skip_qa": {"type": "boolean", "description": "Skip QA review (default false)"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "gstack_list_roles",
        "description": "List all available gstack workflow roles and their slash commands.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _mcp_stdio_loop():
    import sys
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        req_id = req.get("id", 1)
        params = req.get("params", {})

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "gstack-roles", "version": "1.0.0"},
            }}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": GSTACK_TOOLS_SCHEMA}}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            args = params.get("arguments", {})
            if tool_name == "gstack_delegate":
                result = delegate_role(
                    args.get("task", ""), args.get("context", ""),
                    args.get("role_name"), args.get("scope_mode", ""),
                )
                text = json.dumps(result.to_dict(), indent=2)
            elif tool_name == "gstack_pipeline":
                results, dashboard = workflow_pipeline(
                    args.get("task", ""), args.get("context", ""),
                    args.get("skip_ceo", False), args.get("skip_qa", False),
                )
                text = json.dumps({
                    "results": [r.to_dict() for r in results],
                    "dashboard": dashboard.summary(),
                }, indent=2)
            elif tool_name == "gstack_list_roles":
                text = json.dumps(list_roles(), indent=2)
            else:
                text = json.dumps({"error": f"Unknown tool: {tool_name}"})
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {
                "content": [{"type": "text", "text": text}]
            }}
        else:
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(resp), flush=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--mcp":
        _mcp_stdio_loop()
    elif len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
        result = delegate_role(task)
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(json.dumps(list_roles(), indent=2))
