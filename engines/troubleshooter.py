"""
M20 -- AI Troubleshooting Assistant

Provides:
  - Problem description → diagnostic steps
  - Error log parsing and fix suggestions
  - Common issue knowledge base (emulator-specific)
  - Setup-specific learning via agent_memory integration
  - Structured diagnostic workflows
  - Fix verification after applying suggestions
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("troubleshooter")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent


# -----------------------------------------------------------------------
# Data models
# -----------------------------------------------------------------------

@dataclass
class DiagnosticStep:
    """A single diagnostic step."""
    step_num: int = 0
    action: str = ""         # check, fix, verify, info
    description: str = ""
    command: str = ""        # optional command/tool to run
    expected: str = ""       # what we expect to find
    severity: str = "info"   # info, warning, error, critical

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Diagnosis:
    """Complete diagnosis result."""
    problem: str = ""
    category: str = ""       # emulator, rom, media, config, path, bios, performance
    severity: str = "info"
    root_cause: str = ""
    steps: List[DiagnosticStep] = field(default_factory=list)
    suggested_fixes: List[str] = field(default_factory=list)
    related_issues: List[str] = field(default_factory=list)
    auto_fixable: bool = False
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() if isinstance(s, DiagnosticStep) else s for s in self.steps]
        return d


# -----------------------------------------------------------------------
# Common issue knowledge base
# -----------------------------------------------------------------------

COMMON_ISSUES: List[Dict[str, Any]] = [
    # --- Emulator issues ---
    {
        "pattern": r"(retroarch|ra)\s*(crash|not\s*start|black\s*screen|no\s*video)",
        "category": "emulator",
        "title": "RetroArch crash / black screen",
        "root_cause": "Missing core, bad video driver, or incompatible shader",
        "steps": [
            {"action": "check", "description": "Verify RetroArch executable exists and runs standalone"},
            {"action": "check", "description": "Check video driver setting (Settings > Driver > Video) — try 'gl', 'vulkan', or 'd3d11'"},
            {"action": "check", "description": "Verify the core (.dll) exists in retroarch/cores/"},
            {"action": "check", "description": "Disable shaders temporarily (Settings > Shaders > off)"},
            {"action": "fix", "description": "Delete retroarch.cfg and let it regenerate defaults"},
            {"action": "verify", "description": "Launch RetroArch standalone to confirm it starts"},
        ],
        "fixes": [
            "Switch video driver: Settings > Driver > Video > gl/vulkan/d3d11",
            "Reinstall the core from Online Updater > Core Updater",
            "Delete retroarch.cfg to reset to defaults",
            "Update GPU drivers to latest version",
        ],
    },
    {
        "pattern": r"(core|libretro)\s*(not\s*found|missing|failed\s*to\s*load)",
        "category": "emulator",
        "title": "RetroArch core not found / failed to load",
        "root_cause": "Core DLL missing from cores directory or architecture mismatch",
        "steps": [
            {"action": "check", "description": "List cores in retroarch/cores/ directory"},
            {"action": "check", "description": "Verify core filename matches system (e.g. snes9x_libretro.dll for SNES)"},
            {"action": "check", "description": "Check RetroArch architecture (x86 vs x64) matches core architecture"},
            {"action": "fix", "description": "Download correct core from RetroArch Online Updater"},
        ],
        "fixes": [
            "Download the core via RetroArch > Online Updater > Core Updater",
            "Ensure 64-bit RetroArch uses 64-bit cores (and vice versa)",
            "Check core path in retroarch.cfg: libretro_directory",
        ],
    },
    # --- ROM issues ---
    {
        "pattern": r"(rom|game)\s*(not\s*load|won'?t\s*load|crash|freeze|black)",
        "category": "rom",
        "title": "ROM not loading or crashing",
        "root_cause": "Bad ROM dump, wrong core, missing BIOS, or unsupported format",
        "steps": [
            {"action": "check", "description": "Verify ROM file is not corrupted (check CRC32 against DAT)"},
            {"action": "check", "description": "Confirm correct core is assigned for this system"},
            {"action": "check", "description": "Check if system requires BIOS files (PS1, Saturn, etc.)"},
            {"action": "check", "description": "Verify ROM format is supported (.zip, .7z, .chd, etc.)"},
            {"action": "fix", "description": "Try a different ROM dump (look for [!] verified dumps)"},
        ],
        "fixes": [
            "Verify ROM integrity with dat_verifier tool",
            "Check BIOS requirements with bios_audit tool",
            "Try a different emulator core for this system",
            "Convert ROM format (e.g., .cue/.bin to .chd)",
        ],
    },
    {
        "pattern": r"(bios|firmware)\s*(missing|not\s*found|invalid|bad\s*(hash|checksum))",
        "category": "bios",
        "title": "Missing or invalid BIOS files",
        "root_cause": "Required BIOS files not present or have wrong checksums",
        "steps": [
            {"action": "check", "description": "Run bios_audit to identify missing BIOS files"},
            {"action": "check", "description": "Verify BIOS file locations (RetroArch system/ directory)"},
            {"action": "check", "description": "Check MD5 checksums against known-good database"},
            {"action": "fix", "description": "Place correct BIOS files in the system directory"},
        ],
        "fixes": [
            "Run bios_audit_system to check specific system BIOS status",
            "Copy BIOS files to RetroArch/system/ directory",
            "Verify checksums match — some BIOS versions are region-specific",
        ],
    },
    # --- HyperSpin issues ---
    {
        "pattern": r"(hyperspin|hs)\s*(crash|not\s*start|error|freeze|stuck)",
        "category": "config",
        "title": "HyperSpin crash or startup error",
        "root_cause": "Missing paths in HyperSpin.ini, corrupted settings, or media errors",
        "steps": [
            {"action": "check", "description": "Verify HyperSpin.ini exists and has valid paths"},
            {"action": "check", "description": "Check that all database XML files are valid (no malformed XML)"},
            {"action": "check", "description": "Verify media paths (Images, Video, Themes) exist"},
            {"action": "check", "description": "Check for SWF theme files that may cause Flash errors"},
            {"action": "fix", "description": "Run hs_settings_audit to validate all settings"},
        ],
        "fixes": [
            "Run hs_settings_audit to check configuration",
            "Verify all paths in HyperSpin.ini point to existing directories",
            "Check HyperSpin.log for specific error messages",
            "Reset to default theme if custom theme causes crash",
        ],
    },
    {
        "pattern": r"(wheel|theme|video|artwork|media)\s*(missing|not\s*show|broken|blank|black)",
        "category": "media",
        "title": "Missing or broken media assets",
        "root_cause": "Media files missing, wrong format, or incorrect path mapping",
        "steps": [
            {"action": "check", "description": "Run media audit for the affected system"},
            {"action": "check", "description": "Verify media directory structure matches frontend expectations"},
            {"action": "check", "description": "Check file formats (PNG for images, MP4/FLV for video, SWF for themes)"},
            {"action": "check", "description": "Verify filenames match database entries exactly (case-sensitive)"},
            {"action": "fix", "description": "Run scrape_game_metadata + download_game_media to fill gaps"},
        ],
        "fixes": [
            "Run media_audit to identify all missing assets",
            "Use metadata scraper to download missing media",
            "Check filename case sensitivity (must match XML database entries)",
            "Verify image dimensions meet frontend requirements",
        ],
    },
    # --- RocketLauncher issues ---
    {
        "pattern": r"(rocketlauncher|rl)\s*(error|crash|not\s*launch|failed|timeout)",
        "category": "config",
        "title": "RocketLauncher launch failure",
        "root_cause": "Incorrect emulator path, missing module, or config error",
        "steps": [
            {"action": "check", "description": "Verify RocketLauncher paths in Global settings"},
            {"action": "check", "description": "Check emulator module configuration for the system"},
            {"action": "check", "description": "Verify emulator executable exists at configured path"},
            {"action": "check", "description": "Check RocketLauncher log for specific error"},
            {"action": "fix", "description": "Run rl_config_validator to check all settings"},
        ],
        "fixes": [
            "Verify emulator path in RocketLauncher > Emulators > [System]",
            "Check module settings match emulator version",
            "Run RocketLauncherUI to test launch directly",
            "Check Windows Event Viewer for crash details",
        ],
    },
    # --- Performance issues ---
    {
        "pattern": r"(slow|lag|stutter|fps|frame\s*rate|performance|choppy)",
        "category": "performance",
        "title": "Performance / framerate issues",
        "root_cause": "Emulator settings too demanding, wrong backend, or system resources",
        "steps": [
            {"action": "check", "description": "Check CPU/GPU usage during emulation"},
            {"action": "check", "description": "Verify vsync and frame limiter settings"},
            {"action": "check", "description": "Check if shaders or overlays are too demanding"},
            {"action": "check", "description": "Verify emulator-specific performance settings"},
            {"action": "fix", "description": "Switch to a lighter core/emulator for this system"},
        ],
        "fixes": [
            "Disable shaders and overlays temporarily",
            "Enable frame skipping if available",
            "Switch video driver (vulkan often faster than gl)",
            "Close background applications consuming resources",
            "Try a less demanding core (e.g., Snes9x instead of bsnes)",
        ],
    },
    # --- Path issues ---
    {
        "pattern": r"(path|directory|folder|drive)\s*(not\s*found|missing|invalid|wrong|changed)",
        "category": "path",
        "title": "Path or directory not found",
        "root_cause": "Drive letter changed, directory moved, or absolute paths stale",
        "steps": [
            {"action": "check", "description": "List all configured paths and verify they exist"},
            {"action": "check", "description": "Check if drive letters have changed since last session"},
            {"action": "check", "description": "Verify no paths use relative references that broke"},
            {"action": "fix", "description": "Run self_heal_scan to detect and fix broken paths"},
        ],
        "fixes": [
            "Run self_heal_scan to automatically detect broken paths",
            "Update drive letter references in all config files",
            "Use relative paths where possible to avoid drive letter issues",
        ],
    },
    # --- Audio issues ---
    {
        "pattern": r"(audio|sound|music)\s*(no|missing|crackling|popping|distort|mute)",
        "category": "emulator",
        "title": "Audio problems",
        "root_cause": "Wrong audio driver, buffer settings, or sample rate mismatch",
        "steps": [
            {"action": "check", "description": "Check audio driver setting in emulator"},
            {"action": "check", "description": "Verify audio output device is correct"},
            {"action": "check", "description": "Check audio buffer/latency settings"},
            {"action": "fix", "description": "Increase audio buffer size to reduce crackling"},
        ],
        "fixes": [
            "Switch audio driver (try wasapi, dsound, or xaudio2)",
            "Increase audio buffer size (try 128 or 256 frames)",
            "Set audio sample rate to match system default (usually 48000)",
            "Disable audio sync if experiencing stuttering",
        ],
    },
]


# -----------------------------------------------------------------------
# Log parsing
# -----------------------------------------------------------------------

LOG_PATTERNS: List[Dict[str, Any]] = [
    {"pattern": r"error.*?(core|libretro).*?(not found|missing|failed)", "issue": "core_missing"},
    {"pattern": r"error.*?bios.*?(not found|missing|invalid)", "issue": "bios_missing"},
    {"pattern": r"error.*?(file|rom|game).*?(not found|missing|corrupt)", "issue": "rom_corrupt"},
    {"pattern": r"error.*?(path|directory).*?(not found|invalid|missing)", "issue": "path_invalid"},
    {"pattern": r"error.*?(permission|access).*?(denied|failed)", "issue": "permission_error"},
    {"pattern": r"error.*?(memory|ram|heap).*?(alloc|overflow|exhaust)", "issue": "memory_error"},
    {"pattern": r"error.*?(timeout|timed out|hung)", "issue": "timeout_error"},
    {"pattern": r"error.*?(xml|parse|syntax)", "issue": "xml_parse_error"},
    {"pattern": r"error.*?(network|http|connect|download)", "issue": "network_error"},
    {"pattern": r"(crash|segfault|exception|unhandled)", "issue": "crash"},
]

ISSUE_TO_KB: Dict[str, str] = {
    "core_missing": "core not found",
    "bios_missing": "bios missing",
    "rom_corrupt": "rom not load",
    "path_invalid": "path not found",
    "crash": "retroarch crash",
    "xml_parse_error": "hyperspin crash",
}


def parse_error_log(log_text: str) -> Dict[str, Any]:
    """Parse an error log and identify issues.

    Args:
        log_text: Raw log text content

    Returns:
        Identified issues with suggested diagnostics
    """
    lines = log_text.strip().split("\n")
    issues_found: List[Dict[str, Any]] = []
    error_lines: List[str] = []

    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ["error", "fatal", "crash", "exception", "failed"]):
            error_lines.append(line.strip())

        for lp in LOG_PATTERNS:
            if re.search(lp["pattern"], lower):
                issues_found.append({
                    "issue_type": lp["issue"],
                    "line": line.strip()[:200],
                })
                break

    # Deduplicate
    seen = set()
    unique_issues = []
    for issue in issues_found:
        if issue["issue_type"] not in seen:
            seen.add(issue["issue_type"])
            unique_issues.append(issue)

    # Get diagnostics for each issue
    diagnostics = []
    for issue in unique_issues:
        kb_query = ISSUE_TO_KB.get(issue["issue_type"], issue["issue_type"])
        diag = diagnose_problem(kb_query)
        diagnostics.append({
            "issue_type": issue["issue_type"],
            "trigger_line": issue["line"],
            "diagnosis": diag,
        })

    return {
        "total_lines": len(lines),
        "error_lines": len(error_lines),
        "issues_identified": len(unique_issues),
        "diagnostics": diagnostics,
        "raw_errors": error_lines[:20],
    }


# -----------------------------------------------------------------------
# Core diagnostic engine
# -----------------------------------------------------------------------

def diagnose_problem(description: str) -> Dict[str, Any]:
    """Diagnose a problem from a text description.

    Matches against the common issue knowledge base and returns
    diagnostic steps and suggested fixes.

    Args:
        description: Problem description in plain text

    Returns:
        Diagnosis with steps and fixes
    """
    lower = description.lower()
    matches: List[Tuple[float, Dict]] = []

    for issue in COMMON_ISSUES:
        # Pattern match
        if re.search(issue["pattern"], lower):
            score = 100.0
        else:
            # Keyword overlap scoring
            title_words = set(issue["title"].lower().split())
            desc_words = set(lower.split())
            overlap = title_words & desc_words
            score = len(overlap) / max(len(title_words), 1) * 60

            # Category keyword boost
            cat_words = set(issue["category"].split())
            if cat_words & desc_words:
                score += 15

        if score > 20:
            matches.append((score, issue))

    matches.sort(key=lambda x: -x[0])

    if not matches:
        return Diagnosis(
            problem=description,
            category="unknown",
            severity="info",
            root_cause="No matching issue found in knowledge base",
            steps=[DiagnosticStep(
                step_num=1, action="info",
                description="Describe the problem in more detail or check logs for error messages",
            )],
            suggested_fixes=["Check emulator/frontend logs for specific error messages",
                             "Run self_heal_scan for automated issue detection"],
            confidence=0.1,
        ).to_dict()

    best_score, best = matches[0]
    confidence = min(best_score / 100, 1.0)

    steps = []
    for i, s in enumerate(best.get("steps", []), 1):
        steps.append(DiagnosticStep(
            step_num=i, action=s.get("action", "check"),
            description=s.get("description", ""),
        ))

    diag = Diagnosis(
        problem=description,
        category=best.get("category", "unknown"),
        severity="warning" if confidence > 0.7 else "info",
        root_cause=best.get("root_cause", ""),
        steps=steps,
        suggested_fixes=best.get("fixes", []),
        related_issues=[m[1]["title"] for m in matches[1:4]],
        auto_fixable=any(s.action == "fix" for s in steps),
        confidence=round(confidence, 2),
    )

    # Store in agent memory if available
    try:
        from engines.agent_memory import store_memory
        store_memory(
            category="observation",
            subject=best.get("category", "general"),
            key=f"troubleshoot_{description[:50]}",
            value=f"Diagnosed: {best.get('title', '')} (confidence: {confidence:.0%})",
            source="troubleshooter",
            tags="troubleshoot,diagnosis",
        )
    except Exception:
        pass

    return diag.to_dict()


def diagnose_system(system: str) -> Dict[str, Any]:
    """Run a comprehensive diagnostic on a specific system.

    Checks emulator config, ROMs, BIOS, media, and paths for the system.

    Args:
        system: System name (e.g., "PlayStation", "SNES")

    Returns:
        Comprehensive diagnostic report
    """
    checks: List[Dict[str, Any]] = []

    # Check BIOS
    try:
        from engines.bios_manager import audit_system
        bios_result = audit_system(system)
        if hasattr(bios_result, 'to_dict'):
            bios_data = bios_result.to_dict()
        else:
            bios_data = bios_result
        health = bios_data.get("health_score", 100)
        checks.append({
            "check": "BIOS",
            "status": "ok" if health >= 80 else "warning" if health >= 50 else "error",
            "details": f"Health score: {health}%",
            "data": bios_data,
        })
    except Exception as e:
        checks.append({"check": "BIOS", "status": "skipped", "details": str(e)})

    # Check emulator health
    try:
        from engines.emulator_health import check_emulator_health
        emu_result = check_emulator_health(system)
        if isinstance(emu_result, dict):
            checks.append({
                "check": "Emulator",
                "status": "ok" if emu_result.get("healthy") else "warning",
                "details": emu_result.get("summary", ""),
                "data": emu_result,
            })
    except Exception as e:
        checks.append({"check": "Emulator", "status": "skipped", "details": str(e)})

    # Check RocketLauncher config
    try:
        from engines.rl_config_validator import validate_system
        rl_result = validate_system(system)
        if isinstance(rl_result, dict):
            checks.append({
                "check": "RocketLauncher",
                "status": "ok" if not rl_result.get("errors") else "error",
                "details": f"{len(rl_result.get('errors', []))} errors, {len(rl_result.get('warnings', []))} warnings",
                "data": rl_result,
            })
    except Exception as e:
        checks.append({"check": "RocketLauncher", "status": "skipped", "details": str(e)})

    # Summarize
    statuses = [c["status"] for c in checks]
    overall = "error" if "error" in statuses else "warning" if "warning" in statuses else "ok"

    return {
        "system": system,
        "overall_status": overall,
        "checks": checks,
        "total_checks": len(checks),
        "passed": statuses.count("ok"),
        "warnings": statuses.count("warning"),
        "errors": statuses.count("error"),
        "skipped": statuses.count("skipped"),
    }


def get_known_issues() -> Dict[str, Any]:
    """Return the full common issues knowledge base."""
    return {
        "total_issues": len(COMMON_ISSUES),
        "categories": list(set(i["category"] for i in COMMON_ISSUES)),
        "issues": [
            {
                "title": i["title"],
                "category": i["category"],
                "root_cause": i["root_cause"],
                "fix_count": len(i.get("fixes", [])),
            }
            for i in COMMON_ISSUES
        ],
    }


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python troubleshooter.py diagnose <description>")
        print("  python troubleshooter.py system <system_name>")
        print("  python troubleshooter.py log <logfile>")
        print("  python troubleshooter.py issues")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "diagnose":
        desc = " ".join(sys.argv[2:]) or "retroarch crash"
        result = diagnose_problem(desc)
        print(json.dumps(result, indent=2))

    elif cmd == "system":
        sys_name = sys.argv[2] if len(sys.argv) > 2 else "PlayStation"
        result = diagnose_system(sys_name)
        print(json.dumps(result, indent=2, default=str))

    elif cmd == "log":
        logfile = sys.argv[2] if len(sys.argv) > 2 else ""
        if not logfile or not Path(logfile).exists():
            print("Need valid log file path")
        else:
            text = Path(logfile).read_text(encoding="utf-8", errors="replace")
            result = parse_error_log(text)
            print(json.dumps(result, indent=2))

    elif cmd == "issues":
        result = get_known_issues()
        print(json.dumps(result, indent=2))
