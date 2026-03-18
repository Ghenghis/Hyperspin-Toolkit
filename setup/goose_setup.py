"""
goose_setup.py — One-shot E2E wirer for the full HyperSpin agentic stack.

Configures and validates the complete integration:
  Goose (orchestrator)
    ├── hyperspin_toolkit  MCP bridge (21 tools)
    ├── cli_anything       CLI-Anything bridge
    ├── nemoclaw_agents    NemoClaw specialist agents
    ├── drive_manager      Multi-drive scanner/manager
    └── openhands_bridge   OpenHands autonomous agent
  All powered by LM Studio local models on RTX 3090 Ti.

Usage:
  python setup/goose_setup.py                # full setup + validation
  python setup/goose_setup.py --validate     # validate only (no writes)
  python setup/goose_setup.py --fix          # auto-fix detected issues
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── Paths ─────────────────────────────────────────────────────────────
TOOLKIT_DIR    = Path(r"D:\hyperspin_toolkit")
SETUP_DIR      = TOOLKIT_DIR / "setup"
ENGINES_DIR    = TOOLKIT_DIR / "engines"
SKILLS_DIR     = Path(r"C:\Users\Admin\AppData\Roaming\Block\goose\config\skills")
GOOSE_CFG      = Path(r"C:\Users\Admin\AppData\Roaming\Block\goose\config\config.yaml")
LMS_MCP_JSON   = Path(r"C:\Users\Admin\.lmstudio\mcp.json")
LMS_SETTINGS   = Path(r"C:\Users\Admin\.lmstudio\settings.json")
LMSTUDIO_API   = "http://localhost:1234/v1"
OLLAMA_API     = "http://localhost:11434"

# ── Console helpers ───────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def err(msg: str)  -> None: print(f"  {RED}✗{RESET} {msg}")
def info(msg: str) -> None: print(f"  {CYAN}→{RESET} {msg}")
def hdr(msg: str)  -> None: print(f"\n{BOLD}{msg}{RESET}")


# ── Checks ────────────────────────────────────────────────────────────

class SetupResult:
    def __init__(self):
        self.passed: list[str] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.failures) == 0


def check_python() -> bool:
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
        return True
    warn(f"Python {v.major}.{v.minor} — recommend 3.10+")
    return True  # non-fatal


def check_toolkit_files(r: SetupResult) -> None:
    hdr("1. Toolkit Files")
    required = {
        "main.py":                  TOOLKIT_DIR / "main.py",
        "mcp_bridge.py":            TOOLKIT_DIR / "mcp_bridge.py",
        "cli_anything_bridge.py":   ENGINES_DIR / "cli_anything_bridge.py",
        "nemoclaw_agents.py":       ENGINES_DIR / "nemoclaw_agents.py",
        "openhands_bridge.py":      ENGINES_DIR / "openhands_bridge.py",
        "llm_detector.py":          ENGINES_DIR / "llm_detector.py",
    }
    for name, path in required.items():
        if path.exists():
            ok(name)
            r.passed.append(name)
        else:
            err(f"{name} — MISSING at {path}")
            r.failures.append(f"Missing: {path}")


def check_skills(r: SetupResult) -> None:
    hdr("2. Goose Skill Files")
    expected = [
        "hyperspin-toolkit",
        "hyperspin-audit",
        "hyperspin-update",
        "hyperspin-optimize",
        "hyperspin-backup",
        "hyperspin-releases",
        "hyperspin-mame",
        "hyperspin-ai",
        "hyperspin-vision",
        "hyperspin-orchestrator",
        "hyperspin-cli-anything",
    ]
    if not SKILLS_DIR.exists():
        err(f"Skills directory not found: {SKILLS_DIR}")
        r.failures.append(f"Missing skills dir: {SKILLS_DIR}")
        return

    for skill in expected:
        skill_file = SKILLS_DIR / skill / "SKILL.md"
        if skill_file.exists():
            ok(f"{skill}/SKILL.md")
            r.passed.append(f"skill:{skill}")
        else:
            err(f"{skill}/SKILL.md — MISSING")
            r.failures.append(f"Missing skill: {skill}")


def check_goose_config(r: SetupResult) -> None:
    hdr("3. Goose config.yaml")
    if not GOOSE_CFG.exists():
        err(f"config.yaml not found: {GOOSE_CFG}")
        r.failures.append("Missing Goose config.yaml")
        return
    ok("config.yaml exists")

    content = GOOSE_CFG.read_text(encoding="utf-8")
    checks = {
        "hyperspin_toolkit extension":  "hyperspin_toolkit:",
        "cli_anything extension":       "cli_anything:",
        "nemoclaw_agents extension":    "nemoclaw_agents:",
        "openhands_bridge wired":       "openhands_bridge.py",
        "provider = lmstudio":          "GOOSE_PROVIDER: lmstudio",
        "model = Devstral-24B":         "Devstral-Small-2-24B",
        "context_length = 131072":      "GOOSE_CONTEXT_LENGTH: 131072",
        "LM Studio base URL":           "GOOSE_LMSTUDIO_BASE_URL",
    }
    for name, token in checks.items():
        if token in content:
            ok(name)
            r.passed.append(f"goose:{name}")
        else:
            err(f"{name} — NOT FOUND")
            r.failures.append(f"Goose config missing: {name}")


def check_lmstudio_mcp(r: SetupResult) -> None:
    hdr("4. LM Studio mcp.json")
    if not LMS_MCP_JSON.exists():
        warn(f"LM Studio mcp.json not found: {LMS_MCP_JSON}")
        r.warnings.append("LM Studio mcp.json missing — LM Studio may not be installed")
        return
    ok("mcp.json exists")

    try:
        data = json.loads(LMS_MCP_JSON.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        for srv in ["hyperspin-toolkit", "nemoclaw-agents", "cli-anything", "openhands"]:
            if srv in servers:
                ok(f"mcpServer: {srv}")
                r.passed.append(f"lms:{srv}")
            else:
                err(f"mcpServer '{srv}' not in mcp.json")
                r.failures.append(f"LM Studio mcp.json missing: {srv}")

        # Check filesystem includes the configured hyperspin root
        try:
            from core.config import get as _cfg_get
            _hs_root = _cfg_get("paths.hyperspin_root", "")
        except (ImportError, ModuleNotFoundError):
            _hs_root = r"D:\Arcade"  # fallback default
        fs = servers.get("filesystem", {})
        fs_args = " ".join(str(a) for a in fs.get("args", []))
        if _hs_root and (_hs_root in fs_args or _hs_root.replace("\\", "\\\\") in fs_args):
            ok(f"filesystem allows {_hs_root}")
        else:
            warn(f"filesystem MCP does not include configured root: {_hs_root}")
            r.warnings.append(f"filesystem MCP missing {_hs_root}")
    except json.JSONDecodeError as e:
        err(f"mcp.json parse error: {e}")
        r.failures.append(f"mcp.json invalid JSON: {e}")


def check_lmstudio_settings(r: SetupResult) -> None:
    hdr("5. LM Studio Settings")
    if not LMS_SETTINGS.exists():
        warn(f"settings.json not found: {LMS_SETTINGS}")
        r.warnings.append("LM Studio settings.json missing")
        return

    try:
        data = json.loads(LMS_SETTINGS.read_text(encoding="utf-8"))
        ctx = data.get("defaultContextLength", {})
        value = ctx.get("value", 0)
        if value >= 131072:
            ok(f"defaultContextLength = {value:,} ({value // 1024}K)")
            r.passed.append("lms:contextLength")
        elif value >= 32768:
            warn(f"defaultContextLength = {value:,} — recommend 131072 (128K) for Qwen3.5")
            r.warnings.append(f"LM Studio context {value} < 131072")
        else:
            err(f"defaultContextLength = {value} — too low, Qwen3.5 needs 131072+")
            r.failures.append(f"LM Studio context length too low: {value}")
    except Exception as e:
        warn(f"Could not parse settings.json: {e}")
        r.warnings.append(f"settings.json parse error: {e}")


def check_lmstudio_api(r: SetupResult) -> None:
    hdr("6. LM Studio API")
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{LMSTUDIO_API}/models",
            headers={"Authorization": "Bearer lm-studio"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = data.get("data", [])
        ok(f"LM Studio running — {len(models)} model(s) loaded")
        if models:
            for m in models[:3]:
                info(f"  Loaded: {m.get('id', '?')}")
        r.passed.append("lms:api_running")
    except Exception:
        warn("LM Studio API not reachable at http://localhost:1234 — start LM Studio first")
        r.warnings.append("LM Studio not running")


def check_ollama_api(r: SetupResult) -> None:
    hdr("7. Ollama API (fallback)")
    try:
        import urllib.request
        with urllib.request.urlopen(f"{OLLAMA_API}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode())
        models = data.get("models", [])
        ok(f"Ollama running — {len(models)} model(s)")
        r.passed.append("ollama:running")
    except Exception:
        warn("Ollama not reachable at http://localhost:11434 — optional fallback")
        r.warnings.append("Ollama not running (optional)")


def check_dependencies(r: SetupResult) -> None:
    hdr("8. Python Dependencies")
    required = ["httpx", "click", "rich"]
    optional = ["torch", "llama_cpp"]
    for pkg in required:
        try:
            __import__(pkg)
            ok(pkg)
            r.passed.append(f"pkg:{pkg}")
        except ImportError:
            err(f"{pkg} — NOT INSTALLED  →  pip install {pkg}")
            r.failures.append(f"Missing package: {pkg}")
    for pkg in optional:
        try:
            __import__(pkg)
            ok(f"{pkg} (optional)")
        except ImportError:
            info(f"{pkg} not installed (optional)")


def check_goose_binary() -> None:
    hdr("9. Goose CLI Binary")
    goose_paths = [
        Path(r"C:\Users\Admin\AppData\Local\Goose\bin\goose.exe"),
        Path(r"C:\Users\Admin\.local\bin\goose.exe"),
    ]
    shutil_path = shutil.which("goose")
    if shutil_path:
        ok(f"goose on PATH: {shutil_path}")
        try:
            result = subprocess.run([shutil_path, "--version"], capture_output=True, text=True, timeout=5)
            ok(f"Version: {result.stdout.strip()}")
        except Exception:
            pass
        return

    for p in goose_paths:
        if p.exists():
            ok(f"Goose binary found: {p}")
            return

    warn("Goose CLI binary not found on PATH")
    warn("Run: setup\\install_goose.ps1 to install Goose v1.27.2")
    warn("Or: winget install Block.Goose")


# ── Auto-fix ──────────────────────────────────────────────────────────

def fix_context_length() -> None:
    """Fix LM Studio context length to 131072."""
    if not LMS_SETTINGS.exists():
        warn("settings.json not found — cannot auto-fix")
        return
    try:
        data = json.loads(LMS_SETTINGS.read_text(encoding="utf-8"))
        data["defaultContextLength"] = {"type": "custom", "value": 131072}
        LMS_SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
        ok("Fixed defaultContextLength → 131072")
    except Exception as e:
        err(f"Failed to fix context length: {e}")


def fix_install_packages() -> None:
    """Install missing Python packages."""
    packages = ["httpx", "click", "rich"]
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            info(f"Installing {pkg}...")
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=False)


# ── Main ──────────────────────────────────────────────────────────────

def run_setup(validate_only: bool = False, auto_fix: bool = False) -> SetupResult:
    print(f"\n{BOLD}{CYAN}{'='*60}")
    print("  HyperSpin Extreme Toolkit — Full Agentic Stack Setup")
    print(f"{'='*60}{RESET}")
    print(f"\n  Stack: Goose + OpenHands + CLI-Anything + NemoClaw")
    print(f"  Provider: LM Studio (local, RTX 3090 Ti, 24 GB VRAM)")
    print(f"  Toolkit: {TOOLKIT_DIR}")
    print(f"  Skills:  {SKILLS_DIR}")
    print(f"  Config:  {GOOSE_CFG}")

    r = SetupResult()
    check_python()
    check_toolkit_files(r)
    check_skills(r)
    check_goose_config(r)
    check_lmstudio_mcp(r)
    check_lmstudio_settings(r)
    check_lmstudio_api(r)
    check_ollama_api(r)
    check_dependencies(r)
    check_goose_binary()

    if auto_fix and not validate_only:
        hdr("Auto-Fix")
        fix_install_packages()
        fix_context_length()

    # Summary
    hdr("Summary")
    print(f"  {GREEN}Passed : {len(r.passed)}{RESET}")
    if r.warnings:
        print(f"  {YELLOW}Warnings: {len(r.warnings)}{RESET}")
        for w in r.warnings:
            print(f"    {YELLOW}⚠{RESET} {w}")
    if r.failures:
        print(f"  {RED}Failed : {len(r.failures)}{RESET}")
        for f in r.failures:
            print(f"    {RED}✗{RESET} {f}")
    else:
        print(f"\n  {GREEN}{BOLD}✓ All checks passed — stack is ready!{RESET}")
        print(f"\n  Start Goose: goose --provider lmstudio")
        print(f"  Or open: Goose Desktop App → Settings → Provider: LM Studio")

    print()
    return r


def run_e2e_test() -> None:
    """Quick end-to-end test: call each MCP bridge and verify JSON response."""
    hdr("E2E Smoke Tests")

    init_msg = json.dumps({"method": "initialize", "id": 1, "jsonrpc": "2.0",
                           "params": {"protocolVersion": "2024-11-05", "capabilities": {}}})
    list_msg = json.dumps({"method": "tools/list", "id": 2, "jsonrpc": "2.0"})
    payload = init_msg + "\n" + list_msg + "\n"

    tests = [
        ("Toolkit MCP",    [sys.executable, str(TOOLKIT_DIR / "mcp_bridge.py")]),
        ("CLI-Anything",   [sys.executable, str(ENGINES_DIR / "cli_anything_bridge.py")]),
        ("NemoClaw Agents",[sys.executable, str(ENGINES_DIR / "nemoclaw_agents.py")]),
        ("OpenHands Bridge",[sys.executable, str(ENGINES_DIR / "openhands_bridge.py")]),
    ]

    for name, cmd in tests:
        try:
            proc = subprocess.run(
                cmd,
                input=payload,
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(TOOLKIT_DIR),
            )
            lines = [l.strip() for l in proc.stdout.strip().split("\n") if l.strip()]
            tool_count = 0
            for line in lines:
                try:
                    resp = json.loads(line)
                    tools = resp.get("result", {}).get("tools", [])
                    if tools:
                        tool_count = len(tools)
                except json.JSONDecodeError:
                    pass
            if tool_count > 0:
                ok(f"{name} — {tool_count} tools")
            elif proc.stdout:
                warn(f"{name} — responded but no tools parsed")
            else:
                err(f"{name} — no output: {proc.stderr[:120]}")
        except subprocess.TimeoutExpired:
            warn(f"{name} — timed out (20s)")
        except Exception as e:
            err(f"{name} — {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HyperSpin Agentic Stack Setup")
    parser.add_argument("--validate", action="store_true", help="Validate only, no writes")
    parser.add_argument("--fix",      action="store_true", help="Auto-fix detected issues")
    parser.add_argument("--e2e",      action="store_true", help="Run E2E smoke tests on MCP bridges")
    args = parser.parse_args()

    result = run_setup(validate_only=args.validate, auto_fix=args.fix)

    if args.e2e:
        run_e2e_test()

    sys.exit(0 if result.ok else 1)
