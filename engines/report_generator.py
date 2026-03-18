"""
M29 -- Automated Report Generator

Provides:
  - Collection health reports (HTML, Markdown, JSON)
  - Per-system audit summaries
  - Media coverage reports
  - BIOS status reports
  - Completion tracking reports
  - Scheduled report generation
  - Trend analysis (compare snapshots over time)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("report_generator")

TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = TOOLKIT_ROOT / "reports"


# -----------------------------------------------------------------------
# Report templates
# -----------------------------------------------------------------------

def _md_header(title: str, level: int = 1) -> str:
    return f"{'#' * level} {title}\n\n"


def _md_table(headers: List[str], rows: List[List[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines) + "\n\n"


def _md_status_badge(value: float, thresholds: tuple = (80, 50)) -> str:
    if value >= thresholds[0]:
        return f"✅ {value:.1f}%"
    elif value >= thresholds[1]:
        return f"⚠️ {value:.1f}%"
    else:
        return f"❌ {value:.1f}%"


# -----------------------------------------------------------------------
# Data collection helpers
# -----------------------------------------------------------------------

def _collect_bios_data() -> Optional[Dict]:
    try:
        from engines.bios_manager import audit_all
        return audit_all()
    except Exception as e:
        logger.debug("BIOS data unavailable: %s", e)
        return None


def _collect_completion_data() -> Optional[Dict]:
    try:
        from engines.rom_completion import completion_overview
        return completion_overview()
    except Exception as e:
        logger.debug("Completion data unavailable: %s", e)
        return None


def _collect_memory_stats() -> Optional[Dict]:
    try:
        from engines.agent_memory import get_memory_stats
        return get_memory_stats()
    except Exception as e:
        logger.debug("Memory stats unavailable: %s", e)
        return None


def _collect_scheduler_status() -> Optional[Dict]:
    try:
        from engines.scheduler import get_scheduler_status
        return get_scheduler_status()
    except Exception as e:
        logger.debug("Scheduler status unavailable: %s", e)
        return None


def _collect_integrity_data() -> Optional[Dict]:
    try:
        from engines.integrity_checker import get_last_report
        return get_last_report()
    except Exception as e:
        logger.debug("Integrity data unavailable: %s", e)
        return None


# -----------------------------------------------------------------------
# Report generators
# -----------------------------------------------------------------------

def generate_health_report(format: str = "markdown",
                           output_path: str = "") -> Dict[str, Any]:
    """Generate a comprehensive collection health report.

    Args:
        format: Output format — 'markdown', 'json', or 'html'
        output_path: Path to save the report (optional)

    Returns:
        Report content and metadata
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    sections: Dict[str, Any] = {}

    # Collect data from all available engines
    bios = _collect_bios_data()
    if bios:
        sections["bios"] = bios

    completion = _collect_completion_data()
    if completion:
        sections["completion"] = completion

    memory = _collect_memory_stats()
    if memory:
        sections["agent_memory"] = memory

    scheduler = _collect_scheduler_status()
    if scheduler:
        sections["scheduler"] = scheduler

    # Build report
    if format == "json":
        content = json.dumps({
            "title": "HyperSpin Toolkit — Collection Health Report",
            "generated": timestamp,
            "sections": sections,
        }, indent=2)
    elif format == "html":
        content = _render_html_report(timestamp, sections)
    else:
        content = _render_markdown_report(timestamp, sections)

    # Save if path given
    if not output_path:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ext = {"markdown": "md", "json": "json", "html": "html"}.get(format, "md")
        output_path = str(REPORTS_DIR / f"health_report_{now.strftime('%Y%m%d_%H%M%S')}.{ext}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "report_path": output_path,
        "format": format,
        "sections": list(sections.keys()),
        "generated": timestamp,
        "size_bytes": len(content.encode("utf-8")),
    }


def _render_markdown_report(timestamp: str, sections: Dict) -> str:
    md = _md_header("HyperSpin Toolkit — Collection Health Report")
    md += f"*Generated: {timestamp}*\n\n---\n\n"

    # BIOS section
    if "bios" in sections:
        md += _md_header("BIOS Status", 2)
        bios = sections["bios"]
        if isinstance(bios, dict):
            systems = bios.get("systems", [])
            if systems:
                rows = []
                for s in systems[:30]:
                    name = s.get("system", "")
                    health = s.get("health_score", 0)
                    present = s.get("present", 0)
                    total = s.get("total", 0)
                    rows.append([name, _md_status_badge(health), f"{present}/{total}"])
                md += _md_table(["System", "Health", "BIOS Files"], rows)
            summary = bios.get("summary", "")
            if summary:
                md += f"> {summary}\n\n"

    # Completion section
    if "completion" in sections:
        md += _md_header("ROM Set Completion", 2)
        comp = sections["completion"]
        if isinstance(comp, dict):
            per_sys = comp.get("per_system", [])
            if per_sys:
                rows = []
                for s in per_sys[:30]:
                    rows.append([
                        s.get("system", ""),
                        _md_status_badge(s.get("completion_pct", 0)),
                        f"{s.get('owned', 0)}/{s.get('total_in_dat', 0)}",
                        f"{s.get('owned_size_mb', 0):.0f} MB",
                    ])
                md += _md_table(["System", "Completion", "Owned/Total", "Size"], rows)
            overall = comp.get("overall_pct", 0)
            md += f"**Overall: {overall:.1f}%** across {comp.get('systems_tracked', 0)} systems\n\n"

    # Scheduler section
    if "scheduler" in sections:
        md += _md_header("Scheduler Status", 2)
        sched = sections["scheduler"]
        if isinstance(sched, dict):
            md += f"- **Total tasks**: {sched.get('total_tasks', 0)}\n"
            md += f"- **Enabled**: {sched.get('enabled_tasks', 0)}\n"
            md += f"- **Due now**: {sched.get('due_tasks', 0)}\n"
            md += f"- **Unread notifications**: {sched.get('unread_notifications', 0)}\n\n"

    # Agent Memory section
    if "agent_memory" in sections:
        md += _md_header("Agent Knowledge Base", 2)
        mem = sections["agent_memory"]
        if isinstance(mem, dict):
            md += f"- **Total memories**: {mem.get('total_memories', 0)}\n"
            md += f"- **Sessions**: {mem.get('total_sessions', 0)}\n"
            md += f"- **Recommendations**: {mem.get('total_recommendations', 0)} "
            md += f"(acceptance rate: {mem.get('acceptance_rate', 0)}%)\n\n"
            cats = mem.get("by_category", {})
            if cats:
                rows = [[k, str(v)] for k, v in cats.items()]
                md += _md_table(["Category", "Count"], rows)

    md += "---\n\n*Report generated by HyperSpin Toolkit Report Generator (M29)*\n"
    return md


def _render_html_report(timestamp: str, sections: Dict) -> str:
    html = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Collection Health Report</title>
<style>
body { font-family: 'Segoe UI', sans-serif; background: #1a1a2e; color: #e0e0e0; max-width: 900px; margin: 0 auto; padding: 20px; }
h1 { color: #00d4ff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }
h2 { color: #ff6b9d; margin-top: 30px; }
table { border-collapse: collapse; width: 100%; margin: 15px 0; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #333; }
th { background: #16213e; color: #00d4ff; }
tr:hover { background: #16213e; }
.ok { color: #00ff88; } .warn { color: #ffaa00; } .err { color: #ff4444; }
.badge { padding: 2px 8px; border-radius: 4px; font-weight: bold; }
.badge-ok { background: #004422; color: #00ff88; }
.badge-warn { background: #443300; color: #ffaa00; }
.badge-err { background: #440000; color: #ff4444; }
.meta { color: #888; font-size: 0.9em; }
</style></head><body>
"""
    html += f"<h1>Collection Health Report</h1>\n<p class='meta'>Generated: {timestamp}</p>\n"

    if "bios" in sections:
        html += "<h2>BIOS Status</h2>\n"
        bios = sections["bios"]
        if isinstance(bios, dict) and bios.get("systems"):
            html += "<table><tr><th>System</th><th>Health</th><th>Files</th></tr>\n"
            for s in bios["systems"][:30]:
                h = s.get("health_score", 0)
                cls = "ok" if h >= 80 else "warn" if h >= 50 else "err"
                html += f"<tr><td>{s.get('system','')}</td><td class='{cls}'>{h:.0f}%</td>"
                html += f"<td>{s.get('present',0)}/{s.get('total',0)}</td></tr>\n"
            html += "</table>\n"

    if "completion" in sections:
        html += "<h2>ROM Completion</h2>\n"
        comp = sections["completion"]
        if isinstance(comp, dict) and comp.get("per_system"):
            html += "<table><tr><th>System</th><th>Completion</th><th>Owned/Total</th><th>Size</th></tr>\n"
            for s in comp["per_system"][:30]:
                p = s.get("completion_pct", 0)
                cls = "ok" if p >= 80 else "warn" if p >= 50 else "err"
                html += f"<tr><td>{s.get('system','')}</td><td class='{cls}'>{p:.1f}%</td>"
                html += f"<td>{s.get('owned',0)}/{s.get('total_in_dat',0)}</td>"
                html += f"<td>{s.get('owned_size_mb',0):.0f} MB</td></tr>\n"
            html += "</table>\n"

    if "scheduler" in sections:
        html += "<h2>Scheduler</h2>\n<ul>\n"
        sched = sections["scheduler"]
        if isinstance(sched, dict):
            html += f"<li>Tasks: {sched.get('total_tasks',0)} ({sched.get('enabled_tasks',0)} enabled)</li>\n"
            html += f"<li>Due: {sched.get('due_tasks',0)}</li>\n"
            html += f"<li>Notifications: {sched.get('unread_notifications',0)} unread</li>\n"
        html += "</ul>\n"

    html += "<hr><p class='meta'>HyperSpin Toolkit Report Generator (M29)</p>\n</body></html>"
    return html


def generate_system_report(system: str, format: str = "markdown",
                           output_path: str = "") -> Dict[str, Any]:
    """Generate a detailed report for a single system.

    Args:
        system: System name
        format: 'markdown', 'json', or 'html'
        output_path: Save path (optional)

    Returns:
        Report content and metadata
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    data: Dict[str, Any] = {"system": system, "generated": timestamp}

    # BIOS
    try:
        from engines.bios_manager import audit_system
        result = audit_system(system)
        data["bios"] = result.to_dict() if hasattr(result, "to_dict") else result
    except Exception:
        pass

    # Completion
    try:
        from engines.rom_completion import get_missing_roms, get_completion_history
        data["missing_roms"] = get_missing_roms(system, limit=20)
        data["completion_history"] = get_completion_history(system, limit=5)
    except Exception:
        pass

    # Troubleshooting
    try:
        from engines.troubleshooter import diagnose_system
        data["diagnostics"] = diagnose_system(system)
    except Exception:
        pass

    if format == "json":
        content = json.dumps(data, indent=2, default=str)
    else:
        content = _md_header(f"System Report: {system}")
        content += f"*Generated: {timestamp}*\n\n"
        for key, val in data.items():
            if key in ("system", "generated"):
                continue
            content += _md_header(key.replace("_", " ").title(), 2)
            if isinstance(val, dict):
                content += f"```json\n{json.dumps(val, indent=2, default=str)[:2000]}\n```\n\n"
            else:
                content += f"{val}\n\n"

    if not output_path:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        ext = "json" if format == "json" else "md"
        output_path = str(REPORTS_DIR / f"{system}_report_{now.strftime('%Y%m%d')}.{ext}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "report_path": output_path,
        "system": system,
        "format": format,
        "sections": [k for k in data if k not in ("system", "generated")],
        "generated": timestamp,
    }


def generate_comparison_report(systems: List[str],
                               format: str = "markdown") -> Dict[str, Any]:
    """Generate a comparison report across multiple systems.

    Args:
        systems: List of system names to compare
        format: Output format

    Returns:
        Comparison report
    """
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    rows: List[Dict[str, Any]] = []

    for system in systems:
        entry: Dict[str, Any] = {"system": system}

        try:
            from engines.bios_manager import audit_system
            bios = audit_system(system)
            d = bios.to_dict() if hasattr(bios, "to_dict") else bios
            entry["bios_health"] = d.get("health_score", 0)
        except Exception:
            entry["bios_health"] = "N/A"

        rows.append(entry)

    if format == "json":
        content = json.dumps({"systems": rows, "generated": timestamp}, indent=2, default=str)
    else:
        content = _md_header("System Comparison Report")
        content += f"*Generated: {timestamp}*\n\n"
        headers = ["System", "BIOS Health"]
        table_rows = [[r["system"], str(r.get("bios_health", "N/A"))] for r in rows]
        content += _md_table(headers, table_rows)

    output_path = str(REPORTS_DIR / f"comparison_{now.strftime('%Y%m%d')}.md")
    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "report_path": output_path,
        "systems_compared": len(systems),
        "format": format,
        "generated": timestamp,
    }


def list_reports(limit: int = 20) -> Dict[str, Any]:
    """List previously generated reports."""
    if not REPORTS_DIR.exists():
        return {"reports": [], "count": 0}

    reports = []
    for f in sorted(REPORTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if f.is_file():
            reports.append({
                "filename": f.name,
                "path": str(f),
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
            if len(reports) >= limit:
                break

    return {"reports": reports, "count": len(reports)}


# -----------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python report_generator.py health [format]")
        print("  python report_generator.py system <system> [format]")
        print("  python report_generator.py list")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "health":
        fmt = sys.argv[2] if len(sys.argv) > 2 else "markdown"
        result = generate_health_report(fmt)
        print(json.dumps(result, indent=2))

    elif cmd == "system":
        system = sys.argv[2] if len(sys.argv) > 2 else ""
        fmt = sys.argv[3] if len(sys.argv) > 3 else "markdown"
        result = generate_system_report(system, fmt)
        print(json.dumps(result, indent=2))

    elif cmd == "list":
        result = list_reports()
        print(json.dumps(result, indent=2))
