"""MCP Bridge — Exposes HyperSpin Extreme Toolkit as MCP tools for Goose/agents.

This file implements a Model Context Protocol (MCP) server that allows
AI agents like Goose to discover and call our toolkit functions via
structured tool definitions.

Usage with Goose:
  Add to .goose/mcp-servers.json (adjust path to your toolkit location):
  {
    "hyperspin-toolkit": {
      "command": "python",
      "args": ["<TOOLKIT_ROOT>\\mcp_bridge.py"],
      "env": {"TOOLKIT_CONFIG": "<TOOLKIT_ROOT>\\config.yaml"}
    }
  }
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_config, get as cfg_get
from core.logger import get_logger

log = get_logger("mcp_bridge")


# ── Tool Registry ────────────────────────────────────────────────────

def tool_audit_full(**kwargs) -> dict:
    """Run a full HyperSpin ecosystem audit covering systems, ROMs, emulators, media."""
    from engines.auditor import run_full_audit
    return run_full_audit()


def tool_audit_system(system_name: str, **kwargs) -> dict:
    """Audit a specific system by name (e.g., 'MAME', 'Nintendo 64')."""
    from engines.auditor import audit_system
    return audit_system(system_name)


def tool_check_updates(**kwargs) -> list:
    """Check all tracked emulators for available updates via GitHub releases API."""
    from engines.release_checker import check_all_emulators
    return check_all_emulators()


def tool_check_single_update(emulator_name: str, **kwargs) -> dict:
    """Check a specific emulator for updates (e.g., 'MAME', 'PCSX2', 'Dolphin')."""
    from engines.release_checker import check_single_emulator
    result = check_single_emulator(emulator_name)
    return result or {"error": f"Unknown emulator: {emulator_name}"}


def tool_optimize_report(**kwargs) -> dict:
    """Generate a full disk space optimization report with recommendations."""
    from engines.space_optimizer import full_optimization_report
    return full_optimization_report()


def tool_find_duplicates(directory: str = None, **kwargs) -> dict:
    """Find duplicate ROM files by hash. Optionally specify a directory to scan."""
    from engines.space_optimizer import find_duplicate_roms
    dirs = [directory] if directory else None
    return find_duplicate_roms(rom_dirs=dirs)


def tool_find_redundant_emulators(**kwargs) -> dict:
    """Find emulators with multiple installed versions that waste disk space."""
    from engines.space_optimizer import find_redundant_emulators
    return find_redundant_emulators()


def tool_find_large_files(min_size_mb: int = 500, **kwargs) -> list:
    """Find the largest files in the collection. Default minimum: 500 MB."""
    from engines.space_optimizer import find_large_files
    return find_large_files(min_size_mb=min_size_mb)


def tool_discover_external_tools(**kwargs) -> dict:
    """Check which external tools are installed (MAME, Igir, Flips, 7z, etc.)."""
    from engines.external_tools import discover_tools
    return discover_tools()


def tool_backup_create(source: str, label: str = "agent-backup", **kwargs) -> dict:
    """Create a versioned backup of a directory before making changes."""
    from engines.backup import create_backup
    return create_backup(source, label=label)


def tool_get_stats(**kwargs) -> dict:
    """Get collection statistics: system count, ROM count, emulator count, etc."""
    from core import database as db
    systems = db.execute("SELECT COUNT(*) as cnt FROM systems")
    roms = db.execute("SELECT SUM(rom_count) as cnt FROM systems")
    emulators = db.execute("SELECT COUNT(*) as cnt FROM emulators")
    healthy = db.execute("SELECT COUNT(*) as cnt FROM emulators WHERE is_healthy=1")
    backups = db.execute("SELECT COUNT(*) as cnt FROM backups")
    return {
        "systems": systems[0]["cnt"] if systems else 0,
        "total_roms": roms[0]["cnt"] or 0 if roms else 0,
        "emulators": emulators[0]["cnt"] if emulators else 0,
        "healthy_emulators": healthy[0]["cnt"] if healthy else 0,
        "backups": backups[0]["cnt"] if backups else 0,
    }


def tool_disk_usage(**kwargs) -> dict:
    """Get disk usage summary for the D:\\ Arcade drive."""
    from engines.space_optimizer import disk_usage_summary
    return disk_usage_summary()


def tool_mame_version(**kwargs) -> dict:
    """Get installed MAME version and path."""
    from engines.external_tools import MAMETool
    mame = MAMETool()
    if not mame.available:
        return {"error": "MAME not found", "installed": False}
    return {"installed": True, "version": mame.get_version(), "path": mame.exe}


def tool_mame_listxml(output_file: str = None, **kwargs) -> dict:
    """Run MAME -listxml and save output. Required for rebuilding HyperSpin MAME database."""
    from engines.external_tools import MAMETool
    from core.config import get as cfg_get
    from pathlib import Path as _Path
    mame = MAMETool()
    if not mame.available:
        return {"error": "MAME not found", "installed": False}
    out = output_file or str(_Path(cfg_get("paths.output_root", "")) / "mame_listxml.xml")
    result = mame.list_xml(out)
    if result["success"]:
        size_mb = round(_Path(out).stat().st_size / (1024 * 1024), 1) if _Path(out).exists() else 0
        return {"success": True, "output_file": out, "size_mb": size_mb}
    return {"success": False, "error": result.get("stderr", "")[:500]}


def tool_drives_scan(min_gb: float = 100, **kwargs) -> dict:
    """Scan all connected drives and identify which contain arcade content."""
    from engines.drive_index import scan_drives, load_index
    idx = load_index()
    drives = scan_drives(min_gb=min_gb)
    return {
        "drives": drives,
        "current_assignments": {
            "primary":   idx.get("primary"),
            "secondary": idx.get("secondary"),
            "tertiary":  idx.get("tertiary"),
            "primary_path":   f"{idx['primary']}:\\{idx.get('arcade_root','Arcade')}" if idx.get("primary") else None,
        },
    }


def tool_drives_status(**kwargs) -> dict:
    """Show current drive role assignments (primary/secondary/tertiary) with live disk usage."""
    from engines.drive_index import drive_status
    return drive_status()


def tool_drives_set(role: str, letter: str, root: str = "Arcade", **kwargs) -> dict:
    """Assign a drive letter to a role. Saves to drives.json and reloads config."""
    from engines.drive_index import assign_role, _detect_arcade_content
    from core.config import reload_config
    import os
    letter = str(letter).upper().strip(":\\")
    if not os.path.exists(f"{letter}:\\"):
        return {"success": False, "error": f"Drive {letter}: is not connected"}
    if root == "Arcade":
        info = _detect_arcade_content(letter)
        if info.get("found"):
            root = info["arcade_root"]
    idx = assign_role(role, letter, root)
    reload_config()
    fp = idx["roles"].get(role, "")
    return {"success": True, "role": role, "letter": letter, "root": root,
            "path": f"{letter}:\\{root}", "fingerprint": fp}


def tool_drives_plan(source_root: str, dest_drive: str,
                     categories: list | None = None, **kwargs) -> dict:
    """Calculate space required to transfer a collection to a different drive."""
    from engines.drive_transfer import plan_space
    cats = categories or ["all"]
    return plan_space(source_root, dest_drive, cats)


def tool_drives_health(letter: str, **kwargs) -> dict:
    """Check SMART health, temperature, reallocated sectors for a drive."""
    from engines.drive_transfer import drive_health_check
    return drive_health_check(letter)


def tool_drives_migrate(
    source_root: str,
    dest_root:   str,
    categories:  list | None = None,
    verify:      bool = False,
    dry_run:     bool = True,
    **kwargs
) -> dict:
    """
    Start a collection migration from source_root to dest_root.
    Dry-run by default for safety — set dry_run=False to actually copy.
    Resumes automatically if previous transfer was interrupted.
    """
    from engines.drive_transfer import (
        plan_space, build_plan, execute_transfer, transfer_summary,
        rewrite_ini_paths,
    )
    from pathlib import Path as _Path
    cats = categories or ["all"]
    dest_letter = _Path(dest_root).drive.rstrip(":\\") if _Path(dest_root).drive else dest_root[0]

    # Space check
    space = plan_space(source_root, dest_letter, cats)
    if not space["fits"] and not dry_run:
        return {
            "success": False,
            "error":  f"Not enough space: need {space['needed_human']}, "
                      f"have {space['available_human']} free",
            "space":  space,
        }

    plan = build_plan(source_root, dest_root, cats, verify=verify)
    pending = sum(1 for f in plan.files if f.status == "pending")
    result = execute_transfer(plan, verify=verify, dry_run=dry_run)
    summary = transfer_summary(result, plan)

    # Auto rewrite INI paths on real copy
    ini_rewrite = None
    if not dry_run and result.copied > 0:
        src_letter = _Path(source_root).drive.rstrip(":\\")
        dst_letter = _Path(dest_root).drive.rstrip(":\\")
        if src_letter.upper() != dst_letter.upper():
            rl_root = _Path(dest_root) / "RocketLauncher"
            if rl_root.exists():
                ini_rewrite = rewrite_ini_paths(str(rl_root), src_letter, dst_letter)

    return {
        "success":    result.failed == 0,
        "dry_run":    dry_run,
        "space":      space,
        "pending_files": pending,
        "summary":    summary,
        "ini_rewrite": ini_rewrite,
        "next_step":  "Run drives_set to switch the toolkit to the new drive." if not dry_run else
                      "Set dry_run=false to execute the actual copy.",
    }


def tool_drives_compare(source_root: str, dest_root: str,
                        check_size: bool = True, **kwargs) -> dict:
    """
    Compare two directory trees to see what's missing or out of sync.
    Returns counts and sample file lists for missing, extra, and size-mismatched files.
    Use after migration to verify completeness, or before sync to see what will be copied.
    """
    from engines.drive_transfer import compare_drives
    return compare_drives(source_root, dest_root, check_size=check_size)


def tool_drives_sync(
    source_root:  str,
    dest_root:    str,
    delete_extra: bool = False,
    verify:       bool = False,
    dry_run:      bool = True,
    **kwargs
) -> dict:
    """
    Incremental sync: copy files from source_root to dest_root that are missing or
    have a different size on dest. Only changed/new files are copied — existing
    current files are skipped (much faster than a full migrate for day-to-day updates).

    delete_extra=True enables mirror mode (deletes orphaned files on dest).
    dry_run=True by default for safety.
    """
    from engines.drive_transfer import sync_drives, _human
    result = sync_drives(
        source_root, dest_root,
        delete_extra=delete_extra,
        verify=verify,
        dry_run=dry_run,
    )
    elapsed = result.elapsed_sec
    speed_bps = result.bytes_copied / elapsed if elapsed > 0 else 0
    return {
        "success":       result.failed == 0,
        "dry_run":       dry_run,
        "copied":        result.copied,
        "skipped":       result.skipped,
        "failed":        result.failed,
        "bytes_copied":  result.bytes_copied,
        "bytes_human":   _human(result.bytes_copied),
        "speed_human":   _human(int(speed_bps)) + "/s",
        "elapsed_sec":   round(elapsed, 1),
        "verified_ok":   result.verified_ok,
        "verified_fail": result.verified_fail,
        "errors":        result.errors[:20],
        "note": "Set dry_run=false to execute." if dry_run else "Sync complete.",
    }


# ── Drives Reconcile + Index Handlers ──────────────────────────────

def tool_drives_reconcile(detect_type: bool = False, **kwargs) -> dict:
    """Run full drive reconciliation: re-scan, detect letter changes, discover new drives, heal role assignments."""
    from engines.drive_index import reconcile
    idx = reconcile(detect_type=detect_type)
    return {
        "success": True,
        "events": idx.get("events", []),
        "roles": idx.get("roles", {}),
        "total_indexed": len(idx.get("drives", {})),
    }


def tool_drives_list_indexed(**kwargs) -> dict:
    """List all indexed drives including disconnected ones. Shows fingerprints, roles, types, and history."""
    from engines.drive_index import list_indexed_drives
    drives = list_indexed_drives()
    return {"drives": drives, "total": len(drives)}


# ── M8 — ROM Audit Handlers ──────────────────────────────────────────

def tool_rom_verify(rom_dir: str, dat_path: str, system_name: str = "", use_sha1: bool = False, **kwargs) -> dict:
    """M8 — Verify ROMs in a directory against a DAT file. Returns verified/bad/missing/extra counts and per-ROM details."""
    from engines.rom_audit import verify_roms
    result = verify_roms(rom_dir, dat_path, use_sha1=use_sha1, system_name=system_name)
    # Strip full per-ROM details for MCP (too large); keep summary + first 50 results
    if "results" in result and len(result["results"]) > 50:
        result["results"] = result["results"][:50]
        result["results_truncated"] = True
    return result


def tool_rom_verify_all(dat_dir: str | None = None, use_sha1: bool = False, **kwargs) -> dict:
    """M8 — Batch ROM verification: verify all systems that have both a ROM directory and a DAT file."""
    from engines.rom_audit import verify_all_systems
    return verify_all_systems(dat_dir=dat_dir, use_sha1=use_sha1)


# ── M10 — XML Tools Handlers ─────────────────────────────────────────

def tool_xml_validate(xml_path: str, **kwargs) -> dict:
    """M10 — Validate a HyperSpin XML database file."""
    from engines.xml_tools import validate_xml
    return validate_xml(xml_path)


def tool_xml_merge(xml_paths: list[str], output_path: str, dedup: bool = True, sort: bool = True, **kwargs) -> dict:
    """M10 — Merge multiple HyperSpin XML databases into one."""
    from engines.xml_tools import merge_xml
    return merge_xml(xml_paths, output_path, dedup=dedup, sort=sort)


def tool_xml_rebuild(rom_dir: str, output_path: str, reference_xml: str = "", system_name: str = "", **kwargs) -> dict:
    """M10 — Rebuild a HyperSpin XML from a ROM directory."""
    from engines.xml_tools import rebuild_xml
    return rebuild_xml(rom_dir, output_path, reference_xml=reference_xml or None, system_name=system_name)


def tool_xml_filter(xml_path: str, rom_dir: str, output_path: str = "", **kwargs) -> dict:
    """M10 — Filter XML to only games with ROMs present."""
    from engines.xml_tools import filter_xml
    return filter_xml(xml_path, rom_dir, output_path or None)


def tool_xml_stats(xml_path: str, **kwargs) -> dict:
    """M10 — Return statistics for a HyperSpin XML database."""
    from engines.xml_tools import stats_xml
    return stats_xml(xml_path)


# ── M9 — Media Audit Handlers ────────────────────────────────────────

def tool_media_audit_system(system_name: str, check_corruption: bool = True, check_orphans: bool = True, **kwargs) -> dict:
    """M9 — Audit media completeness for a single system: wheel, video, theme, artwork coverage, corruption, orphans."""
    from engines.media_auditor import audit_media_for_system
    result = audit_media_for_system(
        system_name,
        check_corruption=check_corruption,
        check_orphans=check_orphans,
    )
    # Trim issues list for MCP response size
    if "issues" in result and len(result["issues"]) > 50:
        result["issues"] = result["issues"][:50]
        result["issues_truncated"] = True
    return result


def tool_media_audit_all(check_corruption: bool = True, check_orphans: bool = True, **kwargs) -> dict:
    """M9 — Batch media audit across all systems with XML databases."""
    from engines.media_auditor import audit_all_media
    return audit_all_media(check_corruption=check_corruption, check_orphans=check_orphans)


# ── M7 — Emulator Health Handlers ───────────────────────────────────

def tool_emulator_health_all(
    emu_root: str | None = None,
    rl_root: str | None = None,
    **kwargs
) -> dict:
    """M7 — Run a deep health check on all emulator directories: EXEs, version, INI configs, RL modules."""
    from engines.emulator_health import health_summary
    return health_summary(emu_root=emu_root, rl_root=rl_root)


def tool_emulator_health_single(name_or_path: str, **kwargs) -> dict:
    """M7 — Deep health check for a single emulator by name or full path."""
    from engines.emulator_health import check_single_emulator
    return check_single_emulator(name_or_path)


# ── M16 — LLM Detection Handlers ─────────────────────────────────────

def tool_llm_models_scan(provider: str = "all", **kwargs) -> dict:
    """M16 — Scan for local LLM models across LM Studio and Ollama. Returns model names, families, quantization, context windows."""
    from engines.llm_detector import scan_lmstudio_models, scan_ollama_models
    results: dict = {}
    if provider in ("all", "lmstudio"):
        try:
            models = scan_lmstudio_models()
            results["lmstudio"] = [m if isinstance(m, dict) else m.__dict__ for m in models]
        except Exception as exc:
            results["lmstudio"] = {"error": str(exc)}
    if provider in ("all", "ollama"):
        try:
            models = scan_ollama_models()
            results["ollama"] = [m if isinstance(m, dict) else m.__dict__ for m in models]
        except Exception as exc:
            results["ollama"] = {"error": str(exc)}
    total = sum(
        len(v) for v in results.values() if isinstance(v, list)
    )
    return {"providers": results, "total_models": total}


def tool_llm_status(**kwargs) -> dict:
    """M16 — Check LLM provider connectivity (LM Studio, Ollama) and count available models."""
    from core.config import get as cfg_get
    lmstudio_url = cfg_get("ai.lmstudio.base_url", None) or cfg_get("ai.lmstudio_url", "http://localhost:1234")
    ollama_url   = cfg_get("ai.ollama.base_url",   None) or cfg_get("ai.ollama_url",   "http://localhost:11434")
    # Strip /v1 suffix for connectivity check if present
    lmstudio_base = lmstudio_url.rstrip("/").removesuffix("/v1")
    result = {}
    try:
        import httpx
        for name, base_url, path in [
            ("lmstudio", lmstudio_base, "/v1/models"),
            ("ollama",   ollama_url,    "/api/tags"),
        ]:
            try:
                resp = httpx.get(f"{base_url}{path}", timeout=3.0)
                result[name] = {"online": resp.status_code == 200, "url": base_url}
            except Exception:
                result[name] = {"online": False, "url": base_url}
    except ImportError:
        result = {"error": "httpx not installed", "lmstudio": {"online": False}, "ollama": {"online": False}}
    return result


# ── Plugin Tool Handlers ────────────────────────────────────────────

def tool_plugin_list(**kwargs) -> dict:
    """List all loaded plugins with their status."""
    from plugins import manager as pm
    return {"plugins": pm.list_plugins(), "total": len(pm.plugins)}


def tool_plugin_discover(**kwargs) -> dict:
    """Discover all available plugins in the plugins directory."""
    from plugins import manager as pm
    return {"available": pm.discover()}


def tool_plugin_enable(name: str, **kwargs) -> dict:
    """Enable a plugin by name."""
    from plugins import manager as pm
    ok = pm.enable(name)
    return {"name": name, "enabled": ok}


def tool_plugin_disable(name: str, **kwargs) -> dict:
    """Disable an enabled plugin."""
    from plugins import manager as pm
    ok = pm.disable(name)
    return {"name": name, "disabled": ok}


def tool_plugin_info(name: str, **kwargs) -> dict:
    """Get detailed information about a loaded plugin."""
    from plugins import manager as pm
    plugin = pm.get_plugin(name)
    if not plugin:
        return {"error": f"Plugin '{name}' not loaded"}
    return {"plugin": plugin.to_dict()}


def tool_plugin_create(name: str, author: str = "", **kwargs) -> dict:
    """Create a new plugin scaffold from template."""
    from plugins import manager as pm
    try:
        path = pm.create_plugin_scaffold(name, author)
        return {"created": True, "path": path}
    except FileExistsError as exc:
        return {"created": False, "error": str(exc)}


def tool_plugin_events(**kwargs) -> dict:
    """List all active event bus subscriptions."""
    from plugins import manager as pm
    events = pm.event_bus.list_events()
    return {
        "events": {e: pm.event_bus.listener_count(e) for e in events},
        "total_events": len(events),
    }


def tool_plugin_events_subscribe(event: str, plugin_name: str = "mcp_bridge", **kwargs) -> dict:
    """Subscribe to an event on the event bus (registers a no-op listener so the event appears in list_events)."""
    from plugins import manager as pm
    pm.event_bus.subscribe(event, lambda **kw: None, owner=plugin_name)
    return {"subscribed": True, "event": event, "owner": plugin_name,
            "listener_count": pm.event_bus.listener_count(event)}


def tool_plugin_events_emit(event: str, data: dict | None = None, **kwargs) -> dict:
    """Emit an event on the event bus. All registered listeners will be called with the provided data."""
    from plugins import manager as pm
    payload = data or {}
    pm.event_bus.emit(event, **payload)
    return {"emitted": True, "event": event, "data": payload,
            "listener_count": pm.event_bus.listener_count(event)}


def tool_plugin_call_tool(tool_name: str, arguments: dict | None = None, **kwargs) -> dict:
    """Call a tool registered by a plugin."""
    from plugins import manager as pm
    args = arguments or {}
    for tool in pm.get_all_tools():
        if tool["name"] == tool_name:
            return tool["handler"](**args)
    return {"error": f"Plugin tool '{tool_name}' not found"}


# ── M11 — Update Applier Handlers ─────────────────────────────────

def tool_update_check(emulator_name: str | None = None, **kwargs) -> dict:
    """M11 — Check one or all emulators for available updates."""
    from engines.update_applier import check_updates
    return check_updates(emulator_name)


def tool_update_download(emulator_name: str, target_dir: str | None = None, **kwargs) -> dict:
    """M11 — Download the latest release asset for an emulator."""
    from engines.update_applier import download_emulator_update
    return download_emulator_update(emulator_name, target_dir=target_dir)


def tool_update_apply(emulator_name: str, update_source: str, method: str = "auto",
                      test_cmd: str | None = None, dry_run: bool = False, **kwargs) -> dict:
    """M11 — Full update pipeline: snapshot → apply → test → commit/rollback."""
    from engines.update_applier import apply_update
    return apply_update(emulator_name, update_source, method=method,
                        test_cmd=test_cmd, dry_run=dry_run)


def tool_update_rollback(update_id: int, **kwargs) -> dict:
    """M11 — Rollback a previously applied update by its database ID."""
    from engines.update_applier import rollback_update
    return rollback_update(update_id)


def tool_update_status(**kwargs) -> dict:
    """M11 — Get update pipeline status: pending queue + recent history."""
    from engines.update_applier import get_update_status
    return get_update_status()


# ── M17 — AI Natural Language Query Handlers ──────────────────────

def tool_nl_query(question: str, provider: str | None = None, **kwargs) -> dict:
    """M17 — Translate a natural-language question about the collection into SQL, execute, and explain."""
    from engines.nl_query import nl_query
    return nl_query(question, provider=provider)


def tool_ai_recommend(task: str = "agentic", provider: str = "any", **kwargs) -> dict:
    """M17 — Recommend the best local LLM model for a given task."""
    from engines.nl_query import recommend_model_for_task
    return recommend_model_for_task(task, provider)


def tool_ai_report(**kwargs) -> dict:
    """M17 — Generate a comprehensive AI/LLM status report with per-task recommendations."""
    from engines.nl_query import full_ai_report
    return full_ai_report()


# ── M22 — Event Hub Handlers ─────────────────────────────────────

def tool_events_recent(limit: int = 50, event_type: str | None = None, **kwargs) -> dict:
    """M22 — Get recent real-time events from the event hub ring buffer."""
    from engines.event_hub import get_hub
    hub = get_hub()
    events = hub.recent(limit=limit, event_type=event_type)
    return {"events": events, "count": len(events), "clients": hub.client_count}


def tool_events_emit(event_type: str, data: dict | None = None, **kwargs) -> dict:
    """M22 — Emit a custom event to all connected WebSocket clients and listeners."""
    from engines.event_hub import get_hub
    hub = get_hub()
    hub.emit(event_type, data or {})
    return {"emitted": True, "event": event_type, "clients": hub.client_count}


# ── M15 — Automated Rollback Handlers ──────────────────────────────

def tool_rollback_check(emulator_name: str, test_cmd: str | None = None,
                         emu_root: str | None = None, **kwargs) -> dict:
    """M15 — Run post-update health checks for an emulator."""
    from engines.auto_rollback import run_health_checks
    return run_health_checks(emulator_name, test_cmd=test_cmd, emu_root=emu_root)


def tool_rollback_trigger(emulator_name: str, trigger_reason: str = "manual",
                           update_id: int | None = None,
                           backup_path: str | None = None,
                           emu_root: str | None = None, **kwargs) -> dict:
    """M15 — Trigger an automated rollback for an emulator."""
    from engines.auto_rollback import auto_rollback
    return auto_rollback(emulator_name, trigger_reason, update_id=update_id,
                         backup_path=backup_path, emu_root=emu_root)


def tool_rollback_post_update(emulator_name: str, update_id: int | None = None,
                               test_cmd: str | None = None,
                               emu_root: str | None = None, **kwargs) -> dict:
    """M15 — Post-update check: verify health and auto-rollback if needed."""
    from engines.auto_rollback import post_update_check
    return post_update_check(emulator_name, update_id=update_id,
                             test_cmd=test_cmd, emu_root=emu_root)


def tool_rollback_policy(emulator_name: str, auto_rollback_enabled: bool = True,
                          health_check_required: bool = True,
                          test_cmd: str = "", max_rollback_age_hours: int = 72,
                          **kwargs) -> dict:
    """M15 — Set or update rollback policy for an emulator."""
    from engines.auto_rollback import set_policy
    return set_policy(emulator_name, auto_rollback_enabled=auto_rollback_enabled,
                      health_check_required=health_check_required,
                      test_cmd=test_cmd, max_rollback_age_hours=max_rollback_age_hours)


def tool_rollback_list(emulator_name: str | None = None, limit: int = 20, **kwargs) -> dict:
    """M15 — List rollback log entries."""
    from engines.auto_rollback import list_rollbacks
    return {"rollbacks": list_rollbacks(emulator_name=emulator_name, limit=limit)}


def tool_rollback_summary(**kwargs) -> dict:
    """M15 — Rollback system summary."""
    from engines.auto_rollback import rollback_summary
    return rollback_summary()


# ── M14 — Snapshot Verification Handlers ────────────────────────────

def tool_snapshot_capture(target_path: str, name: str | None = None,
                          snapshot_type: str = "manual",
                          compute_hashes: bool = True, **kwargs) -> dict:
    """M14 — Capture a directory snapshot (files, sizes, hashes)."""
    from engines.snapshot_verify import capture_snapshot
    snap = capture_snapshot(target_path, name=name, snapshot_type=snapshot_type,
                            compute_hashes=compute_hashes)
    return snap.to_dict()


def tool_snapshot_compare(pre_name: str, post_name: str, **kwargs) -> dict:
    """M14 — Compare two snapshots and return the diff."""
    from engines.snapshot_verify import compare_snapshots
    diff = compare_snapshots(pre_name, post_name)
    return diff.to_dict()


def tool_snapshot_verify(target_path: str, pre_name: str,
                         expected_changes: list | None = None, **kwargs) -> dict:
    """M14 — Verify an update by capturing post-snapshot and comparing with pre."""
    from engines.snapshot_verify import verify_update
    return verify_update(target_path, pre_name, expected_changes=expected_changes)


def tool_snapshot_list(snapshot_type: str | None = None, limit: int = 50, **kwargs) -> dict:
    """M14 — List recorded snapshots."""
    from engines.snapshot_verify import list_snapshots
    return {"snapshots": list_snapshots(snapshot_type=snapshot_type, limit=limit)}


def tool_snapshot_summary(**kwargs) -> dict:
    """M14 — Snapshot system summary."""
    from engines.snapshot_verify import snapshot_summary
    return snapshot_summary()


# ── M13 — Dependency Conflict Detector Handlers ────────────────────

def tool_deps_report(emu_root: str | None = None, **kwargs) -> dict:
    """M13 — Full dependency analysis report: DLLs, conflicts, runtime usage."""
    from engines.dependency_detector import dependency_report
    return dependency_report(emu_root)


def tool_deps_conflicts(emu_root: str | None = None, **kwargs) -> dict:
    """M13 — Detect DLL version conflicts across emulators."""
    from engines.dependency_detector import detect_conflicts, scan_all_dependencies
    dep_map = scan_all_dependencies(emu_root)
    conflicts = detect_conflicts(dep_map)
    return {"conflicts": [c.to_dict() for c in conflicts], "count": len(conflicts)}


def tool_deps_check_update(emulator_name: str, update_dir: str | None = None,
                            emu_root: str | None = None, **kwargs) -> dict:
    """M13 — Check if updating an emulator would introduce dependency conflicts."""
    from engines.dependency_detector import check_update_conflicts
    return check_update_conflicts(emulator_name, update_dir=update_dir, emu_root=emu_root)


def tool_deps_summary(emu_root: str | None = None, **kwargs) -> dict:
    """M13 — Quick dependency summary: counts and conflict overview."""
    from engines.dependency_detector import dependency_summary
    return dependency_summary(emu_root)


# ── M12 — Version Tracker Handlers ──────────────────────────────────

def tool_version_scan(emu_root: str | None = None, **kwargs) -> dict:
    """M12 — Scan all emulator directories, detect versions, persist to DB."""
    from engines.version_tracker import scan_emulator_versions
    return {"emulators": scan_emulator_versions(emu_root)}


def tool_version_outdated(**kwargs) -> dict:
    """M12 — Check all tracked emulators against GitHub for available updates."""
    from engines.version_tracker import get_outdated
    return get_outdated()


def tool_version_stage(emulator_name: str, target_dir: str | None = None, **kwargs) -> dict:
    """M12 — Download an update to quarantine staging area (does not apply)."""
    from engines.version_tracker import stage_update
    return stage_update(emulator_name, target_dir=target_dir)


def tool_version_quarantine(emulator_name: str | None = None, **kwargs) -> dict:
    """M12 — List quarantined (staged) updates, optionally filtered by emulator."""
    from engines.version_tracker import list_quarantine
    return {"quarantine": list_quarantine(emulator_name)}


def tool_version_apply_staged(quarantine_id: int, test_cmd: str | None = None,
                               dry_run: bool = False, **kwargs) -> dict:
    """M12 — Apply a quarantined update: verify → backup → apply → test."""
    from engines.version_tracker import apply_staged_update
    return apply_staged_update(quarantine_id, test_cmd=test_cmd, dry_run=dry_run)


def tool_version_reject(quarantine_id: int, **kwargs) -> dict:
    """M12 — Reject and delete a quarantined update."""
    from engines.version_tracker import reject_quarantine
    return reject_quarantine(quarantine_id)


def tool_version_history(emulator_name: str, limit: int = 20, **kwargs) -> dict:
    """M12 — Get version history for an emulator."""
    from engines.version_tracker import get_version_history
    return {"history": get_version_history(emulator_name, limit=limit)}


def tool_version_summary(**kwargs) -> dict:
    """M12 — Get version tracking summary: tracked count, quarantined, recent changes."""
    from engines.version_tracker import tracker_summary
    return tracker_summary()


# ── M9 — RocketLauncher Config Validator Handlers ──────────────────

def tool_rl_validate(rl_root: str | None = None, **kwargs) -> dict:
    """M9 — Full RocketLauncher configuration validation."""
    from engines.rl_config_validator import validate_rl
    return validate_rl(rl_root).to_dict()


def tool_rl_validate_system(system_name: str, rl_root: str | None = None, **kwargs) -> dict:
    """M9 — Validate RL config for a single system."""
    from engines.rl_config_validator import validate_single_system
    return validate_single_system(system_name, rl_root)


def tool_rl_orphaned(rl_root: str | None = None, **kwargs) -> dict:
    """M9 — Find orphaned RL settings and missing system mappings."""
    from engines.rl_config_validator import find_orphaned_settings
    return find_orphaned_settings(rl_root)


def tool_rl_summary(rl_root: str | None = None, **kwargs) -> dict:
    """M9 — Quick RL configuration health summary."""
    from engines.rl_config_validator import rl_summary
    return rl_summary(rl_root)


# ── M55 — BIOS Management Handlers ──────────────────────────────────

def tool_bios_audit(systems: list | None = None, **kwargs) -> dict:
    """M55 — Run a full BIOS audit across all known systems or a subset."""
    from engines.bios_manager import full_bios_audit
    report = full_bios_audit(systems=systems)
    return report.to_dict()


def tool_bios_system(system: str, **kwargs) -> dict:
    """M55 — Audit BIOS files for a single system."""
    from engines.bios_manager import audit_system
    result = audit_system(system)
    return result.to_dict()


def tool_bios_missing(**kwargs) -> dict:
    """M55 — Get a summary of all missing BIOS files across systems."""
    from engines.bios_manager import get_missing_bios_summary
    return get_missing_bios_summary()


def tool_bios_list_systems(**kwargs) -> dict:
    """M55 — List all systems with known BIOS requirements."""
    from engines.bios_manager import list_systems
    return {"systems": list_systems()}


# ── M56 — DAT File Verification Handlers ────────────────────────────

def tool_dat_verify_system(system: str, rom_dir: str, dat_path: str,
                           use_sha1: bool = False, **kwargs) -> dict:
    """M56 — Verify a system's ROM set against a DAT file with completion tracking and 1G1R."""
    from engines.dat_verifier import verify_system
    comp = verify_system(system, rom_dir, dat_path, use_sha1=use_sha1)
    return comp.to_dict()


def tool_dat_index(dat_dir: str, **kwargs) -> dict:
    """M56 — Index all DAT files in a directory and return metadata."""
    from engines.dat_verifier import get_dat_summary
    return get_dat_summary(dat_dir)


def tool_dat_metadata(dat_path: str, **kwargs) -> dict:
    """M56 — Parse metadata from a single DAT file (source, version, game count)."""
    from engines.dat_verifier import parse_dat_metadata
    from pathlib import Path as _Path
    return parse_dat_metadata(_Path(dat_path)).to_dict()


def tool_dat_1g1r(dat_path: str, region_priority: list | None = None, **kwargs) -> dict:
    """M56 — Curate a 1G1R set from a DAT file with configurable region priority."""
    from engines.dat_verifier import curate_1g1r
    from engines.rom_audit import parse_dat_file
    from pathlib import Path as _Path
    entries = parse_dat_file(_Path(dat_path))
    result = curate_1g1r(entries, region_priority=region_priority)
    return {"total": len(result), "games": [r.to_dict() for r in result[:100]],
            "truncated": len(result) > 100}


# ── M57 — HyperSpin Settings Handlers ──────────────────────────────

def tool_hs_settings_validate(hs_root: str | None = None, **kwargs) -> dict:
    """M57 — Validate all HyperSpin settings (main INI + per-system)."""
    from engines.hyperspin_settings import audit_all_settings
    report = audit_all_settings(hs_root)
    return report.to_dict()


def tool_hs_settings_get(ini_path: str, section: str, key: str, **kwargs) -> dict:
    """M57 — Read a single setting from a HyperSpin INI file."""
    from engines.hyperspin_settings import get_setting
    from pathlib import Path as _Path
    val = get_setting(_Path(ini_path), section, key)
    return {"section": section, "key": key, "value": val}


def tool_hs_settings_set(ini_path: str, section: str, key: str, value: str, **kwargs) -> dict:
    """M57 — Write a single setting to a HyperSpin INI file."""
    from engines.hyperspin_settings import set_setting
    from pathlib import Path as _Path
    ok = set_setting(_Path(ini_path), section, key, value)
    return {"success": ok, "section": section, "key": key, "value": value}


def tool_hs_settings_preset(ini_path: str, preset: str, **kwargs) -> dict:
    """M57 — Apply a settings preset (performance, quality, cabinet) to a HyperSpin INI."""
    from engines.hyperspin_settings import apply_preset
    from pathlib import Path as _Path
    ok = apply_preset(_Path(ini_path), preset)
    return {"success": ok, "preset": preset}


def tool_hs_settings_systems(hs_root: str | None = None, **kwargs) -> dict:
    """M57 — List all systems with HyperSpin Settings INI files."""
    from engines.hyperspin_settings import list_configured_systems
    systems = list_configured_systems(hs_root)
    return {"systems": systems, "count": len(systems)}


# ── M63 — Self-Healing Framework Handlers ────────────────────────────

def tool_heal_diagnose(hs_root: str | None = None, checks: list | None = None, **kwargs) -> dict:
    """M63 — Run diagnostic checks on HyperSpin installation and report all issues."""
    from engines.self_healer import run_diagnostics
    report = run_diagnostics(hs_root, checks=checks)
    return report.to_dict()


def tool_heal_repair(hs_root: str | None = None, dry_run: bool = True,
                     categories: list | None = None, **kwargs) -> dict:
    """M63 — Auto-repair detected issues. Dry-run by default for safety."""
    from engines.self_healer import heal
    report = heal(hs_root, dry_run=dry_run, categories=categories)
    return report.to_dict()


def tool_heal_history(output_dir: str | None = None, **kwargs) -> dict:
    """M63 — View history of previous healing/repair operations."""
    from engines.self_healer import load_healing_history
    history = load_healing_history(output_dir)
    return {"reports": history[:20], "total": len(history)}


def tool_heal_checks(**kwargs) -> dict:
    """M63 — List all registered diagnostic checks and repair capabilities."""
    from engines.self_healer import list_checks, list_repair_prefixes
    return {"checks": list_checks(), "repair_prefixes": list_repair_prefixes()}


# ── MCP Tool Definitions ────────────────────────────────────────────

TOOLS = [
    {
        "name": "audit_full",
        "description": "Run a full HyperSpin ecosystem audit covering all 184 systems, 173 emulators, ROMs, media, and XML databases. Returns health scores and issues.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_audit_full,
    },
    {
        "name": "audit_system",
        "description": "Audit a specific system by name. Returns ROM count, media status, XML match, health score.",
        "inputSchema": {
            "type": "object",
            "properties": {"system_name": {"type": "string", "description": "System name, e.g. 'MAME', 'Nintendo 64'"}},
            "required": ["system_name"],
        },
        "handler": tool_audit_system,
    },
    {
        "name": "check_all_updates",
        "description": "Check all 20+ tracked emulators for available updates via GitHub releases API. Returns version comparison for each.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_check_updates,
    },
    {
        "name": "check_emulator_update",
        "description": "Check a specific emulator for updates. Known emulators: MAME, RetroArch, Dolphin, PCSX2, RPCS3, PPSSPP, Cemu, Snes9x, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {"emulator_name": {"type": "string", "description": "Emulator name exactly as registered"}},
            "required": ["emulator_name"],
        },
        "handler": tool_check_single_update,
    },
    {
        "name": "optimize_report",
        "description": "Generate a full disk space optimization report. Finds redundant emulators, empty dirs, and provides recommendations. Critical when disk space is low.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_optimize_report,
    },
    {
        "name": "find_duplicates",
        "description": "Find duplicate ROM files by hash across directories. Returns duplicate groups with recoverable space.",
        "inputSchema": {
            "type": "object",
            "properties": {"directory": {"type": "string", "description": "Directory to scan (optional, defaults to full collection)"}},
        },
        "handler": tool_find_duplicates,
    },
    {
        "name": "find_redundant_emulators",
        "description": "Find emulators with multiple installed versions. Shows which to keep and potential space savings.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_find_redundant_emulators,
    },
    {
        "name": "find_large_files",
        "description": "Find the largest files in the collection. Useful for identifying space hogs.",
        "inputSchema": {
            "type": "object",
            "properties": {"min_size_mb": {"type": "integer", "description": "Minimum file size in MB (default: 500)", "default": 500}},
        },
        "handler": tool_find_large_files,
    },
    {
        "name": "discover_tools",
        "description": "Check which external tools are installed: MAME, Igir, Flips, Skyscraper, 7z, Python, Node, Git.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_discover_external_tools,
    },
    {
        "name": "backup_create",
        "description": "Create a versioned backup of a directory BEFORE making any changes. Always backup before upgrades.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Full path to directory to backup"},
                "label": {"type": "string", "description": "Label for this backup (e.g., 'pre-mame-upgrade')", "default": "agent-backup"},
            },
            "required": ["source"],
        },
        "handler": tool_backup_create,
    },
    {
        "name": "get_stats",
        "description": "Get collection statistics: system count, total ROMs, emulator count, healthy emulators, backup count.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_get_stats,
    },
    {
        "name": "disk_usage",
        "description": "Get disk usage summary for the arcade drive. Shows used/free/total and top directories by size.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_disk_usage,
    },
    {
        "name": "mame_version",
        "description": "Get the installed MAME version and executable path.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_mame_version,
    },
    {
        "name": "mame_listxml",
        "description": "Run MAME -listxml to generate the full MAME game database XML. Required for rebuilding the HyperSpin MAME database. Takes 2-5 minutes. Output saved to file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "output_file": {"type": "string", "description": "Path to save the XML output (optional, defaults to output_root/mame_listxml.xml)"},
            },
        },
        "handler": tool_mame_listxml,
    },
    {
        "name": "drives_scan",
        "description": "Scan all connected drives and identify which contain arcade/HyperSpin content. Returns drive letters, sizes (1TB–20TB), labels, arcade content detected, and current role assignments.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_gb": {"type": "number", "description": "Minimum drive size in GB to include (default: 100)", "default": 100},
            },
        },
        "handler": tool_drives_scan,
    },
    {
        "name": "drives_status",
        "description": "Show current drive role assignments (primary/secondary/tertiary) with live disk usage and whether each drive is connected.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_drives_status,
    },
    {
        "name": "drives_set",
        "description": "Assign a drive letter to a role (primary, secondary, or tertiary). Use when the user connects a different HDD or drive letters change.",
        "inputSchema": {
            "type": "object",
            "required": ["role", "letter"],
            "properties": {
                "role":   {"type": "string", "enum": ["primary", "secondary", "tertiary"]},
                "letter": {"type": "string", "description": "Drive letter (single char, e.g. E)"},
                "root":   {"type": "string", "description": "Arcade subfolder on the drive (default: Arcade)", "default": "Arcade"},
            },
        },
        "handler": tool_drives_set,
    },
    {
        "name": "drives_plan",
        "description": "Calculate how much space is needed to copy the arcade collection to a new drive. Returns needed vs available space and whether it fits. Use before drives_migrate.",
        "inputSchema": {
            "type": "object",
            "required": ["source_root", "dest_drive"],
            "properties": {
                "source_root": {"type": "string", "description": "Source arcade root (e.g. D:\\Arcade)"},
                "dest_drive":  {"type": "string", "description": "Destination drive letter (e.g. E)"},
                "categories":  {"type": "array", "items": {"type": "string"},
                                "description": "Subset to measure: all, roms, emulators, media, hyperspin, rocketlauncher"},
            },
        },
        "handler": tool_drives_plan,
    },
    {
        "name": "drives_migrate",
        "description": "Copy the arcade collection from one drive to another. Resumes interrupted transfers automatically. Rewrites RocketLauncher INI paths after copy. ALWAYS set dry_run=true first to preview.",
        "inputSchema": {
            "type": "object",
            "required": ["source_root", "dest_root"],
            "properties": {
                "source_root": {"type": "string", "description": "Source path e.g. D:\\Arcade"},
                "dest_root":   {"type": "string", "description": "Destination path e.g. E:\\Arcade"},
                "categories":  {"type": "array", "items": {"type": "string"},
                                "description": "all / roms / emulators / media / hyperspin / rocketlauncher"},
                "verify":   {"type": "boolean", "description": "Hash-verify files after copy (slower)", "default": False},
                "dry_run":  {"type": "boolean", "description": "Preview only, no files copied (default: true for safety)", "default": True},
            },
        },
        "handler": tool_drives_migrate,
    },
    {
        "name": "drives_health",
        "description": "Check HDD/SSD health using SMART data (status, temperature, reallocated sectors, power-on hours). Works via wmic (built-in) + smartctl if installed.",
        "inputSchema": {
            "type": "object",
            "required": ["letter"],
            "properties": {
                "letter": {"type": "string", "description": "Drive letter to check (e.g. D)"},
            },
        },
        "handler": tool_drives_health,
    },
    {
        "name": "drives_compare",
        "description": "Compare two directory trees and report files missing on dest, files only on dest, and size mismatches. Use after migration to verify completeness, or before sync to preview what will be copied.",
        "inputSchema": {
            "type": "object",
            "required": ["source_root", "dest_root"],
            "properties": {
                "source_root": {"type": "string", "description": "Source directory path (e.g. D:\\Arcade)"},
                "dest_root":   {"type": "string", "description": "Destination directory path (e.g. E:\\Arcade)"},
                "check_size":  {"type": "boolean", "description": "Compare file sizes (default true)"},
            },
        },
        "handler": tool_drives_compare,
    },
    {
        "name": "drives_sync",
        "description": "Incremental sync: copy only files that are missing or have a different size on dest. Much faster than migrate for day-to-day updates. dry_run=true by default. delete_extra=true enables mirror mode.",
        "inputSchema": {
            "type": "object",
            "required": ["source_root", "dest_root"],
            "properties": {
                "source_root":  {"type": "string", "description": "Source directory (e.g. D:\\Arcade)"},
                "dest_root":    {"type": "string", "description": "Destination directory (e.g. E:\\Arcade)"},
                "delete_extra": {"type": "boolean", "description": "Delete files on dest not in source (mirror mode, default false)"},
                "verify":       {"type": "boolean", "description": "Hash-verify copied files (default false)"},
                "dry_run":      {"type": "boolean", "description": "Preview without copying (default true)"},
            },
        },
        "handler": tool_drives_sync,
    },
    # ── M7 — Emulator Health Tools ──
    {
        "name": "emulator_health_all",
        "description": "M7 — Deep health check for all emulators: verifies EXE exists, detects version, scans INI configs for broken paths, checks RocketLauncher module wiring. Returns per-emulator health scores and critical issues.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emu_root": {"type": "string", "description": "Path to emulators root directory (optional, uses config default)"},
                "rl_root":  {"type": "string", "description": "Path to RocketLauncher root directory (optional)"},
            },
        },
        "handler": tool_emulator_health_all,
    },
    {
        "name": "emulator_health_single",
        "description": "M7 — Deep health check for a single emulator by name (relative to emulators_root) or full absolute path.",
        "inputSchema": {
            "type": "object",
            "required": ["name_or_path"],
            "properties": {
                "name_or_path": {"type": "string", "description": "Emulator name (e.g. 'MAME') or full path (e.g. 'D:\\\\Arcade\\\\Emulators\\\\MAME')"},
            },
        },
        "handler": tool_emulator_health_single,
    },
    # ── M16 — LLM Detection Tools ──
    {
        "name": "llm_models_scan",
        "description": "M16 — Scan for locally installed LLM models across LM Studio and Ollama. Returns model list with family, quantization, context window, vision/coder flags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": ["all", "lmstudio", "ollama"], "description": "Which provider to scan (default: all)", "default": "all"},
            },
        },
        "handler": tool_llm_models_scan,
    },
    {
        "name": "llm_status",
        "description": "M16 — Check connectivity to LLM providers (LM Studio on port 1234, Ollama on port 11434). Returns online/offline status for each.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_llm_status,
    },
    # ── Drives Reconcile + Index Tools ──
    {
        "name": "drives_reconcile",
        "description": "Full drive reconciliation: re-scan all drives, detect letter changes, discover new drives, heal role assignments. Run after connecting/disconnecting a drive.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "detect_type": {"type": "boolean", "description": "Also detect NVMe/SSD/HDD for each drive (slower)", "default": False},
            },
        },
        "handler": tool_drives_reconcile,
    },
    {
        "name": "drives_list_indexed",
        "description": "List all indexed drives including disconnected ones. Shows fingerprints, roles, drive types, arcade content, and connection history.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_drives_list_indexed,
    },
    # ── M8 ROM Audit Tools ──
    {
        "name": "rom_verify",
        "description": "M8 — Verify ROMs in a directory against a DAT/XML file. Returns verified/bad_hash/missing/extra counts, completeness %, and per-ROM details.",
        "inputSchema": {
            "type": "object",
            "required": ["rom_dir", "dat_path"],
            "properties": {
                "rom_dir":     {"type": "string", "description": "Path to ROM directory (e.g. 'D:\\Arcade\\MAME')"},
                "dat_path":    {"type": "string", "description": "Path to DAT/XML file with expected hashes"},
                "system_name": {"type": "string", "description": "System name for labelling (e.g. 'MAME')", "default": ""},
                "use_sha1":    {"type": "boolean", "description": "Also verify SHA1 (slower)", "default": False},
            },
        },
        "handler": tool_rom_verify,
    },
    {
        "name": "rom_verify_all",
        "description": "M8 — Batch ROM verification: auto-detect all systems that have both a ROM directory and a DAT file, verify each. Returns per-system summaries and totals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dat_dir":  {"type": "string", "description": "Directory containing DAT files (default: config paths.dat_root)"},
                "use_sha1": {"type": "boolean", "description": "Also verify SHA1 hashes (slower)", "default": False},
            },
        },
        "handler": tool_rom_verify_all,
    },
    # ── M9 Media Audit Tools ──
    {
        "name": "media_audit_system",
        "description": "M9 — Audit media completeness for a single system: wheel art, video snaps, themes, artwork coverage. Detects missing, corrupt, orphaned, and oversized files.",
        "inputSchema": {
            "type": "object",
            "required": ["system_name"],
            "properties": {
                "system_name":      {"type": "string", "description": "System name (e.g. 'MAME', 'Nintendo 64')"},
                "check_corruption": {"type": "boolean", "description": "Validate file headers for corruption", "default": True},
                "check_orphans":    {"type": "boolean", "description": "Flag media with no matching game in XML", "default": True},
            },
        },
        "handler": tool_media_audit_system,
    },
    {
        "name": "media_audit_all",
        "description": "M9 — Batch media audit across all systems. Returns per-system coverage percentages, missing/corrupt/orphan totals, and worst-coverage systems.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "check_corruption": {"type": "boolean", "description": "Validate file headers for corruption", "default": True},
                "check_orphans":    {"type": "boolean", "description": "Flag media with no matching game in XML", "default": True},
            },
        },
        "handler": tool_media_audit_all,
    },
    # ── M10 XML Tools ──
    {
        "name": "xml_validate",
        "description": "M10 — Validate a HyperSpin XML database: check structure, duplicates, missing fields.",
        "inputSchema": {
            "type": "object",
            "required": ["xml_path"],
            "properties": {
                "xml_path": {"type": "string", "description": "Path to HyperSpin XML database file"},
            },
        },
        "handler": tool_xml_validate,
    },
    {
        "name": "xml_merge",
        "description": "M10 — Merge multiple HyperSpin XML databases into one, dedup by game name.",
        "inputSchema": {
            "type": "object",
            "required": ["xml_paths", "output_path"],
            "properties": {
                "xml_paths":   {"type": "array", "items": {"type": "string"}, "description": "List of XML file paths to merge"},
                "output_path": {"type": "string", "description": "Output merged XML path"},
                "dedup":       {"type": "boolean", "description": "Remove duplicate game names", "default": True},
                "sort":        {"type": "boolean", "description": "Sort games alphabetically", "default": True},
            },
        },
        "handler": tool_xml_merge,
    },
    {
        "name": "xml_rebuild",
        "description": "M10 — Rebuild a HyperSpin XML from a ROM directory, optionally pulling metadata from a reference XML.",
        "inputSchema": {
            "type": "object",
            "required": ["rom_dir", "output_path"],
            "properties": {
                "rom_dir":       {"type": "string", "description": "ROM directory to scan"},
                "output_path":   {"type": "string", "description": "Output XML path"},
                "reference_xml": {"type": "string", "description": "Optional reference XML for metadata"},
                "system_name":   {"type": "string", "description": "System name for header"},
            },
        },
        "handler": tool_xml_rebuild,
    },
    {
        "name": "xml_filter",
        "description": "M10 — Filter a HyperSpin XML to only games with ROMs present in a directory.",
        "inputSchema": {
            "type": "object",
            "required": ["xml_path", "rom_dir"],
            "properties": {
                "xml_path":    {"type": "string", "description": "Source XML file"},
                "rom_dir":     {"type": "string", "description": "ROM directory to check against"},
                "output_path": {"type": "string", "description": "Output path (default: overwrite source)"},
            },
        },
        "handler": tool_xml_filter,
    },
    {
        "name": "xml_stats",
        "description": "M10 — Return statistics for a HyperSpin XML: game count, year range, manufacturers, genres, field completeness.",
        "inputSchema": {
            "type": "object",
            "required": ["xml_path"],
            "properties": {
                "xml_path": {"type": "string", "description": "Path to HyperSpin XML database file"},
            },
        },
        "handler": tool_xml_stats,
    },
    # ── M11 — Update Applier Tools ──
    {
        "name": "update_check",
        "description": "M11 — Check one or all emulators for available updates via GitHub releases. Pass emulator_name for a single check, omit for all.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name (e.g. 'MAME'). Omit to check all tracked emulators."},
            },
        },
        "handler": tool_update_check,
    },
    {
        "name": "update_download",
        "description": "M11 — Download the latest release asset for an emulator from GitHub.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name (e.g. 'MAME', 'RetroArch')"},
                "target_dir": {"type": "string", "description": "Override download directory (optional)"},
            },
        },
        "handler": tool_update_download,
    },
    {
        "name": "update_apply",
        "description": "M11 — Full update pipeline: snapshot → apply → test → commit/rollback. ALWAYS use dry_run=true first.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name", "update_source"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name"},
                "update_source": {"type": "string", "description": "Path to downloaded update file or directory"},
                "method": {"type": "string", "enum": ["auto", "copy", "extract", "script"], "default": "auto"},
                "test_cmd": {"type": "string", "description": "Optional command to verify the update worked"},
                "dry_run": {"type": "boolean", "description": "Snapshot only, do not apply (default: false)", "default": False},
            },
        },
        "handler": tool_update_apply,
    },
    {
        "name": "update_rollback",
        "description": "M11 — Rollback a previously applied update by its database ID. Restores from snapshot.",
        "inputSchema": {
            "type": "object",
            "required": ["update_id"],
            "properties": {
                "update_id": {"type": "integer", "description": "Update history ID to rollback"},
            },
        },
        "handler": tool_update_rollback,
    },
    {
        "name": "update_status",
        "description": "M11 — Get update pipeline status: pending queue and recent history.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_update_status,
    },
    # ── M17 — AI Natural Language Query Tools ──
    {
        "name": "nl_query",
        "description": "M17 — Ask a natural-language question about the collection (e.g. 'how many MAME ROMs are verified?'). Translates to SQL, executes, and explains the result.",
        "inputSchema": {
            "type": "object",
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "description": "Natural language question about the collection"},
                "provider": {"type": "string", "description": "Preferred LLM provider: 'ollama' or 'lmstudio' (optional)"},
            },
        },
        "handler": tool_nl_query,
    },
    {
        "name": "ai_recommend_model",
        "description": "M17 — Recommend the best local LLM model for a task: agentic, coding, reasoning, vision, fast, general.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "enum": ["agentic", "coding", "reasoning", "vision", "fast", "general"], "default": "agentic"},
                "provider": {"type": "string", "enum": ["lmstudio", "ollama", "any"], "default": "any"},
            },
        },
        "handler": tool_ai_recommend,
    },
    {
        "name": "ai_full_report",
        "description": "M17 — Generate comprehensive AI/LLM status report: provider connectivity, model inventory, per-task recommendations.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_ai_report,
    },
    # ── M22 — Real-time Event Hub Tools ──
    {
        "name": "events_recent",
        "description": "M22 — Get recent real-time events from the event hub. Use to check what's happened since last poll.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max events to return (default: 50)", "default": 50},
                "event_type": {"type": "string", "description": "Filter by event type (optional)"},
            },
        },
        "handler": tool_events_recent,
    },
    {
        "name": "events_emit",
        "description": "M22 — Emit a custom event to all connected dashboard WebSocket clients and in-process listeners.",
        "inputSchema": {
            "type": "object",
            "required": ["event_type"],
            "properties": {
                "event_type": {"type": "string", "description": "Event type string (e.g. 'scan.started', 'update.completed')"},
                "data": {"type": "object", "description": "Payload data to include with the event"},
            },
        },
        "handler": tool_events_emit,
    },
    # ── M15 — Automated Rollback Tools ──
    {
        "name": "rollback_check",
        "description": "M15 — Run post-update health checks for an emulator: exe exists, health score, optional test command.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator to check"},
                "test_cmd": {"type": "string", "description": "Custom test command (optional)"},
                "emu_root": {"type": "string", "description": "Override emulators root (optional)"},
            },
        },
        "handler": tool_rollback_check,
    },
    {
        "name": "rollback_trigger",
        "description": "M15 — Trigger an automated rollback: restore from backup, re-run health checks, log the event.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name", "trigger_reason"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator to rollback"},
                "trigger_reason": {"type": "string", "description": "Why the rollback is needed"},
                "update_id": {"type": "integer", "description": "Update history ID (optional)"},
                "backup_path": {"type": "string", "description": "Override backup path (optional)"},
                "emu_root": {"type": "string", "description": "Override emulators root (optional)"},
            },
        },
        "handler": tool_rollback_trigger,
    },
    {
        "name": "rollback_post_update",
        "description": "M15 — Post-update check: verify emulator health and auto-rollback if checks fail.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator to verify"},
                "update_id": {"type": "integer", "description": "Update history ID (optional)"},
                "test_cmd": {"type": "string", "description": "Custom test command (optional)"},
                "emu_root": {"type": "string", "description": "Override emulators root (optional)"},
            },
        },
        "handler": tool_rollback_post_update,
    },
    {
        "name": "rollback_policy",
        "description": "M15 — Set or update rollback policy for an emulator: enable/disable auto-rollback, test commands, max age.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name"},
                "auto_rollback_enabled": {"type": "boolean", "default": True},
                "health_check_required": {"type": "boolean", "default": True},
                "test_cmd": {"type": "string", "description": "Test command to run after updates"},
                "max_rollback_age_hours": {"type": "integer", "default": 72},
            },
        },
        "handler": tool_rollback_policy,
    },
    {
        "name": "rollback_list",
        "description": "M15 — List rollback history with optional emulator filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emulator_name": {"type": "string", "description": "Filter by emulator (optional)"},
                "limit": {"type": "integer", "default": 20},
            },
        },
        "handler": tool_rollback_list,
    },
    {
        "name": "rollback_summary",
        "description": "M15 — Rollback system summary: total rollbacks, policies, status breakdown.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_rollback_summary,
    },
    # ── M14 — Snapshot Verification Tools ──
    {
        "name": "snapshot_capture",
        "description": "M14 — Capture a directory snapshot: file list, sizes, SHA256 hashes. Use before updates to create a baseline.",
        "inputSchema": {
            "type": "object",
            "required": ["target_path"],
            "properties": {
                "target_path": {"type": "string", "description": "Directory to snapshot"},
                "name": {"type": "string", "description": "Snapshot name (auto-generated if omitted)"},
                "snapshot_type": {"type": "string", "enum": ["pre", "post", "manual"], "default": "manual"},
                "compute_hashes": {"type": "boolean", "description": "Compute SHA256 hashes (default true)", "default": True},
            },
        },
        "handler": tool_snapshot_capture,
    },
    {
        "name": "snapshot_compare",
        "description": "M14 — Compare two snapshots and return added/removed/modified files.",
        "inputSchema": {
            "type": "object",
            "required": ["pre_name", "post_name"],
            "properties": {
                "pre_name": {"type": "string", "description": "Pre-update snapshot name"},
                "post_name": {"type": "string", "description": "Post-update snapshot name"},
            },
        },
        "handler": tool_snapshot_compare,
    },
    {
        "name": "snapshot_verify",
        "description": "M14 — Verify an update: capture post-snapshot, compare with pre, flag unexpected changes.",
        "inputSchema": {
            "type": "object",
            "required": ["target_path", "pre_name"],
            "properties": {
                "target_path": {"type": "string", "description": "Directory that was updated"},
                "pre_name": {"type": "string", "description": "Pre-update snapshot name"},
                "expected_changes": {"type": "array", "items": {"type": "string"}, "description": "Relative paths expected to change"},
            },
        },
        "handler": tool_snapshot_verify,
    },
    {
        "name": "snapshot_list",
        "description": "M14 — List recorded snapshots with optional type filter.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "snapshot_type": {"type": "string", "enum": ["pre", "post", "manual"], "description": "Filter by type"},
                "limit": {"type": "integer", "default": 50},
            },
        },
        "handler": tool_snapshot_list,
    },
    {
        "name": "snapshot_summary",
        "description": "M14 — Snapshot system summary: totals by type and status, recent snapshots.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_snapshot_summary,
    },
    # ── M13 — Dependency Conflict Detector Tools ──
    {
        "name": "deps_report",
        "description": "M13 — Full dependency analysis: scan all emulators for shared DLLs, detect version conflicts, map runtime usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emu_root": {"type": "string", "description": "Override emulators root directory (optional)"},
            },
        },
        "handler": tool_deps_report,
    },
    {
        "name": "deps_conflicts",
        "description": "M13 — Detect DLL version conflicts across emulators. Returns list of conflicts with severity and resolution suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emu_root": {"type": "string", "description": "Override emulators root directory (optional)"},
            },
        },
        "handler": tool_deps_conflicts,
    },
    {
        "name": "deps_check_update",
        "description": "M13 — Pre-update conflict check: see if updating an emulator would introduce dependency issues.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator to check"},
                "update_dir": {"type": "string", "description": "Path to update files to compare (optional)"},
                "emu_root": {"type": "string", "description": "Override emulators root (optional)"},
            },
        },
        "handler": tool_deps_check_update,
    },
    {
        "name": "deps_summary",
        "description": "M13 — Quick dependency summary: emulator count, DLL counts, conflict totals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emu_root": {"type": "string", "description": "Override emulators root directory (optional)"},
            },
        },
        "handler": tool_deps_summary,
    },
    # ── M12 — Version Tracker Tools ──
    {
        "name": "version_scan",
        "description": "M12 — Scan all emulator directories, detect installed versions, persist to database. Returns list of emulators with detected versions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emu_root": {"type": "string", "description": "Override emulators root directory (optional)"},
            },
        },
        "handler": tool_version_scan,
    },
    {
        "name": "version_outdated",
        "description": "M12 — Check all tracked emulators against GitHub releases to find those with available updates.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_version_outdated,
    },
    {
        "name": "version_stage",
        "description": "M12 — Download an emulator update to quarantine staging area without applying it.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name (e.g. 'MAME', 'RetroArch')"},
                "target_dir": {"type": "string", "description": "Override quarantine directory (optional)"},
            },
        },
        "handler": tool_version_stage,
    },
    {
        "name": "version_quarantine",
        "description": "M12 — List all quarantined (staged) updates, optionally filtered by emulator name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emulator_name": {"type": "string", "description": "Filter by emulator name (optional)"},
            },
        },
        "handler": tool_version_quarantine,
    },
    {
        "name": "version_apply_staged",
        "description": "M12 — Apply a quarantined update: verify SHA256 → backup current → apply → test → commit/rollback.",
        "inputSchema": {
            "type": "object",
            "required": ["quarantine_id"],
            "properties": {
                "quarantine_id": {"type": "integer", "description": "Quarantine entry ID to apply"},
                "test_cmd": {"type": "string", "description": "Command to verify the update (optional)"},
                "dry_run": {"type": "boolean", "description": "Snapshot only, do not apply", "default": False},
            },
        },
        "handler": tool_version_apply_staged,
    },
    {
        "name": "version_reject",
        "description": "M12 — Reject and delete a quarantined update by its ID.",
        "inputSchema": {
            "type": "object",
            "required": ["quarantine_id"],
            "properties": {
                "quarantine_id": {"type": "integer", "description": "Quarantine entry ID to reject"},
            },
        },
        "handler": tool_version_reject,
    },
    {
        "name": "version_history",
        "description": "M12 — Get version history for a specific emulator, showing all detected version changes over time.",
        "inputSchema": {
            "type": "object",
            "required": ["emulator_name"],
            "properties": {
                "emulator_name": {"type": "string", "description": "Emulator name"},
                "limit": {"type": "integer", "description": "Max records to return", "default": 20},
            },
        },
        "handler": tool_version_history,
    },
    {
        "name": "version_summary",
        "description": "M12 — Get version tracking summary: total tracked emulators, version records, quarantined updates, recent changes.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_version_summary,
    },
    # ── M9 — RocketLauncher Config Validator Tools ──
    {
        "name": "rl_validate",
        "description": "M9 — Full RocketLauncher configuration validation: modules, system mappings, INI paths, plugins. Returns health score and all issues.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rl_root": {"type": "string", "description": "Override RocketLauncher root directory (optional)"},
            },
        },
        "handler": tool_rl_validate,
    },
    {
        "name": "rl_validate_system",
        "description": "M9 — Validate RocketLauncher config for a single system: INI settings, module mapping, path checks.",
        "inputSchema": {
            "type": "object",
            "required": ["system_name"],
            "properties": {
                "system_name": {"type": "string", "description": "System name (e.g. 'MAME', 'Nintendo 64')"},
                "rl_root": {"type": "string", "description": "Override RL root (optional)"},
            },
        },
        "handler": tool_rl_validate_system,
    },
    {
        "name": "rl_orphaned",
        "description": "M9 — Find orphaned RL settings (no matching HyperSpin DB) and missing settings (DB exists but no RL config).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rl_root": {"type": "string", "description": "Override RL root (optional)"},
            },
        },
        "handler": tool_rl_orphaned,
    },
    {
        "name": "rl_summary",
        "description": "M9 — Quick RocketLauncher health summary: module count, system count, health score, issue counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "rl_root": {"type": "string", "description": "Override RL root (optional)"},
            },
        },
        "handler": tool_rl_summary,
    },
    # ── Plugin Management Tools ──
    {
        "name": "plugin_list",
        "description": "List all loaded plugins with their state, version, and status info.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_plugin_list,
    },
    {
        "name": "plugin_discover",
        "description": "Discover all available plugins in the plugins/ directory (both loaded and unloaded).",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_plugin_discover,
    },
    {
        "name": "plugin_enable",
        "description": "Enable a plugin by name. Loads it first if not already loaded. Resolves dependencies automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Plugin name (filename stem without .py)"}},
            "required": ["name"],
        },
        "handler": tool_plugin_enable,
    },
    {
        "name": "plugin_disable",
        "description": "Disable an enabled plugin. Removes its event subscriptions. Fails if other plugins depend on it.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Plugin name to disable"}},
            "required": ["name"],
        },
        "handler": tool_plugin_disable,
    },
    {
        "name": "plugin_info",
        "description": "Get detailed info about a loaded plugin: metadata, state, config defaults, status.",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Plugin name"}},
            "required": ["name"],
        },
        "handler": tool_plugin_info,
    },
    {
        "name": "plugin_create",
        "description": "Create a new plugin scaffold file from template. Generates a ready-to-edit .py file in plugins/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Plugin name (e.g. 'rom_cleaner')"},
                "author": {"type": "string", "description": "Author name (optional)"},
            },
            "required": ["name"],
        },
        "handler": tool_plugin_create,
    },
    {
        "name": "plugin_events",
        "description": "List all active event bus subscriptions and listener counts.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_plugin_events,
    },
    {
        "name": "plugin_call_tool",
        "description": "Call a custom tool registered by a plugin. Use plugin_list to see available plugin tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_name": {"type": "string", "description": "Full tool name (e.g. 'plugin_example_plugin_hello')"},
                "arguments": {"type": "object", "description": "Arguments to pass to the tool"},
            },
            "required": ["tool_name"],
        },
        "handler": tool_plugin_call_tool,
    },
    {
        "name": "plugin_events_subscribe",
        "description": "Subscribe to an event on the plugin event bus. Creates a listener entry so the event appears in plugin_events.",
        "inputSchema": {
            "type": "object",
            "required": ["event"],
            "properties": {
                "event": {"type": "string", "description": "Event name (e.g. 'audit.completed', 'plugin.enabled')"},
                "plugin_name": {"type": "string", "description": "Owner tag for the subscription (default: mcp_bridge)", "default": "mcp_bridge"},
            },
        },
        "handler": tool_plugin_events_subscribe,
    },
    {
        "name": "plugin_events_emit",
        "description": "Emit an event on the plugin event bus. All registered listeners for this event will be called with the provided data.",
        "inputSchema": {
            "type": "object",
            "required": ["event"],
            "properties": {
                "event": {"type": "string", "description": "Event name to emit (e.g. 'audit.started', 'custom.my_event')"},
                "data":  {"type": "object", "description": "Key-value data payload to pass to listeners"},
            },
        },
        "handler": tool_plugin_events_emit,
    },
    # ── M55 — BIOS Management ──
    {
        "name": "bios_audit",
        "description": "M55 — Full BIOS audit across all known systems. Checks MD5 hashes against known-good database, reports valid/bad_hash/missing per file, and computes per-system health scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "systems": {"type": "array", "items": {"type": "string"}, "description": "Optional list of systems to audit (default: all)"},
            },
        },
        "handler": tool_bios_audit,
    },
    {
        "name": "bios_system",
        "description": "M55 — Audit BIOS files for a single system (e.g. 'PlayStation', 'Sega Saturn').",
        "inputSchema": {
            "type": "object",
            "properties": {"system": {"type": "string", "description": "System name"}},
            "required": ["system"],
        },
        "handler": tool_bios_system,
    },
    {
        "name": "bios_missing",
        "description": "M55 — Get summary of all missing BIOS files across systems.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_bios_missing,
    },
    {
        "name": "bios_list_systems",
        "description": "M55 — List all systems with known BIOS requirements in the database.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_bios_list_systems,
    },
    # ── M56 — DAT File Verification ──
    {
        "name": "dat_verify_system",
        "description": "M56 — Verify a system's ROM set against a DAT file. Returns completion %, 1G1R stats, missing/extra game lists.",
        "inputSchema": {
            "type": "object",
            "required": ["system", "rom_dir", "dat_path"],
            "properties": {
                "system": {"type": "string", "description": "System name"},
                "rom_dir": {"type": "string", "description": "Path to ROM directory"},
                "dat_path": {"type": "string", "description": "Path to DAT file"},
                "use_sha1": {"type": "boolean", "description": "Also verify SHA1 hashes", "default": False},
            },
        },
        "handler": tool_dat_verify_system,
    },
    {
        "name": "dat_index",
        "description": "M56 — Index all DAT files in a directory. Returns per-source summary (No-Intro, Redump, TOSEC, MAME) with game/ROM counts.",
        "inputSchema": {
            "type": "object",
            "required": ["dat_dir"],
            "properties": {"dat_dir": {"type": "string", "description": "Directory containing DAT files"}},
        },
        "handler": tool_dat_index,
    },
    {
        "name": "dat_metadata",
        "description": "M56 — Parse metadata from a single DAT file: source, version, author, game count.",
        "inputSchema": {
            "type": "object",
            "required": ["dat_path"],
            "properties": {"dat_path": {"type": "string", "description": "Path to DAT file"}},
        },
        "handler": tool_dat_metadata,
    },
    {
        "name": "dat_1g1r",
        "description": "M56 — Curate a 1G1R (1 Game 1 ROM) set from a DAT file. Picks best region variant per game.",
        "inputSchema": {
            "type": "object",
            "required": ["dat_path"],
            "properties": {
                "dat_path": {"type": "string", "description": "Path to DAT file"},
                "region_priority": {"type": "array", "items": {"type": "string"}, "description": "Region priority order (default: USA first)"},
            },
        },
        "handler": tool_dat_1g1r,
    },
    # ── M57 — HyperSpin Settings ──
    {
        "name": "hs_settings_validate",
        "description": "M57 — Validate all HyperSpin settings: main INI + per-system INIs. Reports broken paths, invalid values, health scores.",
        "inputSchema": {
            "type": "object",
            "properties": {"hs_root": {"type": "string", "description": "HyperSpin root directory (optional)"}},
        },
        "handler": tool_hs_settings_validate,
    },
    {
        "name": "hs_settings_get",
        "description": "M57 — Read a single setting from a HyperSpin INI file.",
        "inputSchema": {
            "type": "object",
            "required": ["ini_path", "section", "key"],
            "properties": {
                "ini_path": {"type": "string", "description": "Path to INI file"},
                "section": {"type": "string", "description": "INI section name"},
                "key": {"type": "string", "description": "Setting key"},
            },
        },
        "handler": tool_hs_settings_get,
    },
    {
        "name": "hs_settings_set",
        "description": "M57 — Write a single setting to a HyperSpin INI file.",
        "inputSchema": {
            "type": "object",
            "required": ["ini_path", "section", "key", "value"],
            "properties": {
                "ini_path": {"type": "string", "description": "Path to INI file"},
                "section": {"type": "string", "description": "INI section name"},
                "key": {"type": "string", "description": "Setting key"},
                "value": {"type": "string", "description": "New value"},
            },
        },
        "handler": tool_hs_settings_set,
    },
    {
        "name": "hs_settings_preset",
        "description": "M57 — Apply a settings preset to HyperSpin.ini. Presets: 'performance', 'quality', 'cabinet'.",
        "inputSchema": {
            "type": "object",
            "required": ["ini_path", "preset"],
            "properties": {
                "ini_path": {"type": "string", "description": "Path to HyperSpin.ini"},
                "preset": {"type": "string", "enum": ["performance", "quality", "cabinet"]},
            },
        },
        "handler": tool_hs_settings_preset,
    },
    {
        "name": "hs_settings_systems",
        "description": "M57 — List all systems that have HyperSpin Settings INI files.",
        "inputSchema": {
            "type": "object",
            "properties": {"hs_root": {"type": "string", "description": "HyperSpin root (optional)"}},
        },
        "handler": tool_hs_settings_systems,
    },
    # ── M63 — Self-Healing Framework ──
    {
        "name": "heal_diagnose",
        "description": "M63 — Run diagnostic checks on HyperSpin installation. Detects missing dirs, broken INI paths, empty databases, missing media.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hs_root": {"type": "string", "description": "HyperSpin root (optional)"},
                "checks": {"type": "array", "items": {"type": "string"}, "description": "Specific checks to run (optional, default: all)"},
            },
        },
        "handler": tool_heal_diagnose,
    },
    {
        "name": "heal_repair",
        "description": "M63 — Auto-repair detected issues. DRY-RUN by default — set dry_run=false to actually fix. Creates backups before modifying.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hs_root": {"type": "string", "description": "HyperSpin root (optional)"},
                "dry_run": {"type": "boolean", "description": "Preview only, don't modify (default: true)", "default": True},
                "categories": {"type": "array", "items": {"type": "string"}, "description": "Only repair these categories (optional)"},
            },
        },
        "handler": tool_heal_repair,
    },
    {
        "name": "heal_history",
        "description": "M63 — View history of previous healing/repair operations.",
        "inputSchema": {
            "type": "object",
            "properties": {"output_dir": {"type": "string", "description": "Report directory (optional)"}},
        },
        "handler": tool_heal_history,
    },
    {
        "name": "heal_checks",
        "description": "M63 — List all registered diagnostic checks and repair capabilities.",
        "inputSchema": {"type": "object", "properties": {}},
        "handler": tool_heal_checks,
    },
]


# ── MCP Server (stdio transport) ────────────────────────────────────

def handle_request(request: dict) -> dict:
    """Process an MCP JSON-RPC request and return a response."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "hyperspin-toolkit", "version": "2.0.0"},
            },
        }

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    elif method == "tools/list":
        tool_list = [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in TOOLS
        ]
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tool_list}}

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        tool = next((t for t in TOOLS if t["name"] == tool_name), None)
        if not tool:
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True},
            }

        try:
            result = tool["handler"](**arguments)
            result_text = json.dumps(result, indent=2, default=str)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": result_text}], "isError": False},
            }
        except Exception as exc:
            error_text = f"Error in {tool_name}: {exc}\n{traceback.format_exc()}"
            log.error(error_text)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": error_text}], "isError": True},
            }

    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    else:
        return {
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def main():
    """Run MCP server on stdio — reads JSON-RPC from stdin, writes to stdout."""
    # Initialize toolkit
    config_path = Path(__file__).parent / "config.yaml"
    if config_path.exists():
        load_config(str(config_path))

    from core import database as db
    try:
        db.init_db()
    except Exception:
        pass  # DB init may fail on first run, that's OK

    log.info("MCP Bridge started — HyperSpin Extreme Toolkit v2.0")

    # Read JSON-RPC messages from stdin
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)

        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
