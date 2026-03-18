"""FastAPI web dashboard for HyperSpin Extreme Toolkit."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get as cfg_get, load_config
from core.logger import get_logger
from core import database as db

log = get_logger("dashboard")

@asynccontextmanager
async def _lifespan(app: FastAPI):
    load_config()
    db.init_db()
    try:
        cfg = load_config()
        plugin_manager.set_config(cfg)
        plugin_manager.load_enabled_from_db()
        plugin_manager.event_bus.emit("dashboard.startup")
    except Exception as exc:
        log.warning("Plugin startup: %s", exc)
    log.info("Dashboard started on http://%s:%s", cfg_get("dashboard.host"), cfg_get("dashboard.port"))
    yield


app = FastAPI(title="HyperSpin Extreme Toolkit", version="2.0.0", lifespan=_lifespan)

# Static files and templates
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# M22 — WebSocket real-time event hub
# ---------------------------------------------------------------------------
from engines.event_hub import get_hub as _get_event_hub


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """M22 — WebSocket endpoint for real-time event push.

    Clients connect here and receive JSON events as they happen:
        {"event": "scan.progress", "data": {...}, "ts": "..."}
    Clients can also send JSON commands:
        {"subscribe": "scan.*"}  — future: per-topic filtering
    """
    await ws.accept()
    hub = _get_event_hub()
    hub.register(ws)
    hub.emit("ws.client_connected", {"clients": hub.client_count})
    try:
        while True:
            data = await ws.receive_text()
            # Acknowledge client messages
            try:
                import json as _json
                msg = _json.loads(data)
                if msg.get("ping"):
                    await ws.send_json({"pong": True, "clients": hub.client_count})
                else:
                    await ws.send_json({"type": "ack", "data": msg})
            except Exception:
                await ws.send_json({"type": "ack", "data": data})
    except WebSocketDisconnect:
        hub.unregister(ws)
        hub.emit("ws.client_disconnected", {"clients": hub.client_count})


async def broadcast(message: dict):
    """Legacy broadcast helper — now delegates to EventHub."""
    hub = _get_event_hub()
    hub.emit("broadcast", message)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/systems", response_class=HTMLResponse)
async def systems_page(request: Request):
    return templates.TemplateResponse("systems.html", {"request": request})


@app.get("/emulators", response_class=HTMLResponse)
async def emulators_page(request: Request):
    return templates.TemplateResponse("emulators.html", {"request": request})


@app.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request):
    return templates.TemplateResponse("backups.html", {"request": request})


@app.get("/updates", response_class=HTMLResponse)
async def updates_page(request: Request):
    return templates.TemplateResponse("updates.html", {"request": request})


@app.get("/health", response_class=HTMLResponse)
async def health_page(request: Request):
    return templates.TemplateResponse("health.html", {"request": request})


@app.get("/ai", response_class=HTMLResponse)
async def ai_page(request: Request):
    return templates.TemplateResponse("ai.html", {"request": request})


# ---------------------------------------------------------------------------
# API — Dashboard stats
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def api_stats():
    try:
        systems = db.execute("SELECT COUNT(*) as cnt FROM systems")
        roms = db.execute("SELECT SUM(rom_count) as cnt FROM systems")
        emulators = db.execute("SELECT COUNT(*) as cnt FROM emulators")
        healthy_emu = db.execute("SELECT COUNT(*) as cnt FROM emulators WHERE is_healthy=1")
        backups = db.execute("SELECT COUNT(*) as cnt FROM backups")
        updates = db.execute("SELECT COUNT(*) as cnt FROM update_history")

        # Health score
        scores = db.execute("SELECT AVG(health_score) as avg_score FROM systems WHERE health_score > 0")
        avg_score = scores[0]["avg_score"] if scores and scores[0]["avg_score"] else 0

        return {
            "total_systems": systems[0]["cnt"] if systems else 0,
            "total_roms": roms[0]["cnt"] if roms and roms[0]["cnt"] else 0,
            "total_emulators": emulators[0]["cnt"] if emulators else 0,
            "healthy_emulators": healthy_emu[0]["cnt"] if healthy_emu else 0,
            "total_backups": backups[0]["cnt"] if backups else 0,
            "total_updates": updates[0]["cnt"] if updates else 0,
            "avg_health_score": round(avg_score, 1),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# API — Systems
# ---------------------------------------------------------------------------

@app.get("/api/systems")
async def api_systems():
    try:
        rows = db.execute("SELECT * FROM systems ORDER BY name")
        return {"systems": rows}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/systems/{system_name}")
async def api_system_detail(system_name: str):
    try:
        rows = db.execute("SELECT * FROM systems WHERE name=?", (system_name,))
        if not rows:
            return JSONResponse({"error": "System not found"}, status_code=404)
        return {"system": rows[0]}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# API — Emulators
# ---------------------------------------------------------------------------

@app.get("/api/emulators")
async def api_emulators():
    try:
        rows = db.execute("SELECT * FROM emulators ORDER BY name")
        return {"emulators": rows}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# API — Backups
# ---------------------------------------------------------------------------

@app.get("/api/backups")
async def api_backups():
    try:
        rows = db.execute("SELECT * FROM backups ORDER BY created_at DESC LIMIT 50")
        return {"backups": rows}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/backups/create")
async def api_create_backup(request: Request):
    try:
        body = await request.json()
        source = body.get("source", cfg_get("paths.hyperspin_root"))
        label = body.get("label", "manual")
        backup_type = body.get("type", "full")

        from engines.backup import create_backup
        result = create_backup(source, label=label, backup_type=backup_type)
        return {"result": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — Updates
# ---------------------------------------------------------------------------

@app.get("/api/updates")
async def api_updates():
    try:
        rows = db.execute("SELECT * FROM update_history ORDER BY created_at DESC LIMIT 50")
        return {"updates": rows}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# API — Audit
# ---------------------------------------------------------------------------

@app.post("/api/audit/full")
async def api_full_audit():
    try:
        from engines.auditor import run_full_audit
        result = run_full_audit()
        return {"result": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/audit/system/{system_name}")
async def api_audit_system(system_name: str):
    try:
        from engines.auditor import audit_system
        result = audit_system(system_name)
        return {"result": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — AI
# ---------------------------------------------------------------------------

@app.get("/api/ai/status")
async def api_ai_status():
    try:
        from engines.ai_engine import get_ai
        ai = get_ai()
        status = ai.detect_available()
        return {"providers": status}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/ai/chat")
async def api_ai_chat(request: Request):
    try:
        body = await request.json()
        message = body.get("message", "")
        provider = body.get("provider")

        from engines.ai_engine import get_ai
        ai = get_ai()
        result = ai.ask(message, provider=provider)
        return {"response": result}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# NOTE: POST /api/ai/query is defined in the M17 section below (engines.nl_query)
# with audit logging and provider support. Do not duplicate here.


# ---------------------------------------------------------------------------
# API — Config
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def api_config():
    try:
        cfg = load_config()
        # Redact sensitive data
        safe = json.loads(json.dumps(cfg, default=str))
        return {"config": safe}
    except Exception as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# API — Plugins
# ---------------------------------------------------------------------------

from plugins import manager as plugin_manager

@app.get("/api/plugins")
async def api_plugins_list():
    """List all loaded plugins with status."""
    try:
        return {"plugins": plugin_manager.list_plugins()}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/plugins/discover")
async def api_plugins_discover():
    """Discover all available plugins (loaded or not)."""
    try:
        return {"available": plugin_manager.discover()}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/plugins/{name}/enable")
async def api_plugin_enable(name: str):
    """Enable a plugin by name."""
    try:
        ok = plugin_manager.enable(name)
        return {"name": name, "enabled": ok}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/plugins/{name}/disable")
async def api_plugin_disable(name: str):
    """Disable a plugin by name."""
    try:
        ok = plugin_manager.disable(name)
        return {"name": name, "disabled": ok}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/plugins/{name}/unload")
async def api_plugin_unload(name: str):
    """Unload a plugin by name."""
    try:
        ok = plugin_manager.unload(name)
        return {"name": name, "unloaded": ok}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/plugins/{name}/info")
async def api_plugin_info(name: str):
    """Get detailed info about a loaded plugin."""
    try:
        plugin = plugin_manager.get_plugin(name)
        if not plugin:
            return JSONResponse({"error": f"Plugin '{name}' not loaded"}, status_code=404)
        return {"plugin": plugin.to_dict()}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/plugins/create")
async def api_plugin_create(request: Request):
    """Create a new plugin scaffold from template."""
    try:
        body = await request.json()
        name = body.get("name", "")
        author = body.get("author", "")
        if not name:
            return JSONResponse({"error": "Plugin name is required"}, status_code=400)
        path = plugin_manager.create_plugin_scaffold(name, author)
        return {"created": True, "path": path}
    except FileExistsError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/plugins/events")
async def api_plugins_events():
    """List active event bus subscriptions."""
    try:
        events = plugin_manager.event_bus.list_events()
        return {
            "events": {e: plugin_manager.event_bus.listener_count(e) for e in events},
            "total_events": len(events),
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M8 ROM Audit
# ---------------------------------------------------------------------------

@app.get("/api/roms/verify")
async def api_rom_verify(rom_dir: str, dat_path: str, system_name: str = "", use_sha1: bool = False):
    """M8 — Verify ROMs in a directory against a DAT file."""
    try:
        from engines.rom_audit import verify_roms
        result = verify_roms(rom_dir, dat_path, use_sha1=use_sha1, system_name=system_name)
        # Truncate per-ROM details for API response size
        if "results" in result and len(result["results"]) > 100:
            result["results"] = result["results"][:100]
            result["results_truncated"] = True
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/roms/verify-all")
async def api_rom_verify_all(dat_dir: str | None = None, use_sha1: bool = False):
    """M8 — Batch ROM verification across all systems with DAT files."""
    try:
        from engines.rom_audit import verify_all_systems
        return verify_all_systems(dat_dir=dat_dir or None, use_sha1=use_sha1)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M9 Media Audit
# ---------------------------------------------------------------------------

@app.get("/api/media/audit/{system_name}")
async def api_media_audit_system(system_name: str, check_corruption: bool = True, check_orphans: bool = True):
    """M9 — Media audit for a single system."""
    try:
        from engines.media_auditor import audit_media_for_system
        result = audit_media_for_system(
            system_name,
            check_corruption=check_corruption,
            check_orphans=check_orphans,
        )
        # Trim issues for API response size
        if "issues" in result and len(result["issues"]) > 100:
            result["issues"] = result["issues"][:100]
            result["issues_truncated"] = True
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/media/audit")
async def api_media_audit_all(check_corruption: bool = True, check_orphans: bool = True):
    """M9 — Batch media audit across all systems."""
    try:
        from engines.media_auditor import audit_all_media
        return audit_all_media(check_corruption=check_corruption, check_orphans=check_orphans)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M10 XML Tools
# ---------------------------------------------------------------------------

@app.get("/api/xml/validate")
async def api_xml_validate(xml_path: str):
    """M10 — Validate a HyperSpin XML database."""
    try:
        from engines.xml_tools import validate_xml
        return validate_xml(xml_path)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/xml/merge")
async def api_xml_merge(request: Request):
    """M10 — Merge multiple HyperSpin XML databases. Body: {xml_paths, output_path, dedup?, sort?}"""
    try:
        from engines.xml_tools import merge_xml
        body = await request.json()
        return merge_xml(
            body["xml_paths"], body["output_path"],
            dedup=body.get("dedup", True), sort=body.get("sort", True),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/xml/rebuild")
async def api_xml_rebuild(request: Request):
    """M10 — Rebuild XML from ROM dir. Body: {rom_dir, output_path, reference_xml?, system_name?}"""
    try:
        from engines.xml_tools import rebuild_xml
        body = await request.json()
        return rebuild_xml(
            body["rom_dir"], body["output_path"],
            reference_xml=body.get("reference_xml") or None,
            system_name=body.get("system_name", ""),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/xml/filter")
async def api_xml_filter(xml_path: str, rom_dir: str, output_path: str = ""):
    """M10 — Filter XML to only games with ROMs present."""
    try:
        from engines.xml_tools import filter_xml
        return filter_xml(xml_path, rom_dir, output_path or None)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/xml/stats")
async def api_xml_stats(xml_path: str):
    """M10 — Return statistics for a HyperSpin XML database."""
    try:
        from engines.xml_tools import stats_xml
        return stats_xml(xml_path)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M7 Emulator Health
# ---------------------------------------------------------------------------

@app.get("/api/emulators/health")
async def api_emulator_health_all(emu_root: str | None = None, rl_root: str | None = None):
    """M7 — Deep health check for all emulators."""
    try:
        from engines.emulator_health import health_summary
        return health_summary(emu_root=emu_root or None, rl_root=rl_root or None)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/emulators/health/{name}")
async def api_emulator_health_single(name: str):
    """M7 — Deep health check for a single emulator by name or path."""
    try:
        from engines.emulator_health import check_single_emulator
        result = check_single_emulator(name)
        if "error" in result:
            return JSONResponse(result, status_code=404)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M16 LLM Detection
# ---------------------------------------------------------------------------

@app.get("/api/ai/llm-status")
async def api_llm_status():
    """M16 — Check LLM provider connectivity (LM Studio, Ollama)."""
    try:
        import httpx
        lmstudio_url = cfg_get("ai.lmstudio.base_url", None) or cfg_get("ai.lmstudio_url", "http://localhost:1234")
        ollama_url   = cfg_get("ai.ollama.base_url",   None) or cfg_get("ai.ollama_url",   "http://localhost:11434")
        # Strip /v1 suffix for base connectivity check
        lmstudio_base = lmstudio_url.rstrip("/").removesuffix("/v1")
        result: dict = {}
        for name, base_url, path in [
            ("lmstudio", lmstudio_base, "/v1/models"),
            ("ollama",   ollama_url,    "/api/tags"),
        ]:
            try:
                resp = httpx.get(f"{base_url}{path}", timeout=3.0)
                result[name] = {"online": resp.status_code == 200, "url": base_url}
            except Exception:
                result[name] = {"online": False, "url": base_url}
        return result
    except ImportError:
        return JSONResponse({"error": "httpx not installed"}, status_code=500)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/ai/models")
async def api_ai_models(provider: str = "all"):
    """M16 — List locally installed LLM models from LM Studio and/or Ollama."""
    try:
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
        total = sum(len(v) for v in results.values() if isinstance(v, list))
        return {"providers": results, "total_models": total}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M11 Update Applier
# ---------------------------------------------------------------------------

@app.get("/api/updates/check")
async def api_updates_check(emulator: str | None = None):
    """M11 — Check one or all emulators for available updates."""
    try:
        from engines.update_applier import check_updates
        return check_updates(emulator)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/updates/download")
async def api_updates_download(request: Request):
    """M11 — Download the latest release for an emulator."""
    try:
        body = await request.json()
        from engines.update_applier import download_emulator_update
        result = download_emulator_update(
            body["emulator_name"],
            target_dir=body.get("target_dir"),
        )
        hub = _get_event_hub()
        hub.emit("update.downloaded", result)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/updates/apply")
async def api_updates_apply(request: Request):
    """M11 — Apply an update: snapshot → apply → test → commit/rollback."""
    try:
        body = await request.json()
        from engines.update_applier import apply_update
        result = apply_update(
            body["emulator_name"],
            body["update_source"],
            method=body.get("method", "auto"),
            test_cmd=body.get("test_cmd"),
            dry_run=body.get("dry_run", False),
        )
        hub = _get_event_hub()
        hub.emit("update.applied", {"emulator": body["emulator_name"], "status": result.get("status")})
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/updates/rollback")
async def api_updates_rollback(request: Request):
    """M11 — Rollback a previously applied update."""
    try:
        body = await request.json()
        from engines.update_applier import rollback_update
        result = rollback_update(body["update_id"])
        hub = _get_event_hub()
        hub.emit("update.rolled_back", result)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/updates/status")
async def api_updates_status():
    """M11 — Get update pipeline status: pending queue + recent history."""
    try:
        from engines.update_applier import get_update_status
        return get_update_status()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M12 Version Tracker
# ---------------------------------------------------------------------------

@app.get("/api/versions/scan")
async def api_versions_scan(emu_root: str | None = None):
    """M12 — Scan all emulator directories, detect and persist versions."""
    try:
        from engines.version_tracker import scan_emulator_versions
        return {"emulators": scan_emulator_versions(emu_root)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/versions/outdated")
async def api_versions_outdated():
    """M12 — Check tracked emulators against GitHub for available updates."""
    try:
        from engines.version_tracker import get_outdated
        return get_outdated()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/versions/stage")
async def api_versions_stage(request: Request):
    """M12 — Download an update to quarantine staging area."""
    try:
        body = await request.json()
        from engines.version_tracker import stage_update
        result = stage_update(body["emulator_name"], target_dir=body.get("target_dir"))
        if not result.get("error"):
            hub = _get_event_hub()
            hub.emit("version.staged", {"emulator": body["emulator_name"], "status": result.get("status")})
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/versions/quarantine")
async def api_versions_quarantine(emulator: str | None = None):
    """M12 — List quarantined (staged) updates."""
    try:
        from engines.version_tracker import list_quarantine
        return {"quarantine": list_quarantine(emulator)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/versions/apply-staged")
async def api_versions_apply_staged(request: Request):
    """M12 — Apply a quarantined update: verify → backup → apply → test."""
    try:
        body = await request.json()
        from engines.version_tracker import apply_staged_update
        result = apply_staged_update(
            body["quarantine_id"],
            test_cmd=body.get("test_cmd"),
            dry_run=body.get("dry_run", False),
        )
        hub = _get_event_hub()
        hub.emit("version.applied", {"quarantine_id": body["quarantine_id"], "status": result.get("status")})
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/versions/reject")
async def api_versions_reject(request: Request):
    """M12 — Reject and delete a quarantined update."""
    try:
        body = await request.json()
        from engines.version_tracker import reject_quarantine
        return reject_quarantine(body["quarantine_id"])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/versions/history/{emulator_name}")
async def api_versions_history(emulator_name: str, limit: int = 20):
    """M12 — Get version history for a specific emulator."""
    try:
        from engines.version_tracker import get_version_history
        return {"history": get_version_history(emulator_name, limit=limit)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/versions/tracked")
async def api_versions_tracked(include_versions: bool = False):
    """M12 — List all tracked emulators from the DB."""
    try:
        from engines.version_tracker import get_all_tracked
        return {"emulators": get_all_tracked(include_versions=include_versions)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/versions/summary")
async def api_versions_summary():
    """M12 — Version tracking summary: tracked count, quarantined, recent changes."""
    try:
        from engines.version_tracker import tracker_summary
        return tracker_summary()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M13 Dependency Conflict Detector
# ---------------------------------------------------------------------------

@app.get("/api/deps/report")
async def api_deps_report(emu_root: str | None = None):
    """M13 — Full dependency analysis report."""
    try:
        from engines.dependency_detector import dependency_report
        return dependency_report(emu_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/deps/conflicts")
async def api_deps_conflicts(emu_root: str | None = None):
    """M13 — Detect DLL version conflicts across emulators."""
    try:
        from engines.dependency_detector import detect_conflicts, scan_all_dependencies
        dep_map = scan_all_dependencies(emu_root)
        conflicts = detect_conflicts(dep_map)
        return {"conflicts": [c.to_dict() for c in conflicts], "count": len(conflicts)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/deps/check-update")
async def api_deps_check_update(request: Request):
    """M13 — Pre-update conflict check for an emulator."""
    try:
        body = await request.json()
        from engines.dependency_detector import check_update_conflicts
        return check_update_conflicts(
            body["emulator_name"],
            update_dir=body.get("update_dir"),
            emu_root=body.get("emu_root"),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/deps/summary")
async def api_deps_summary(emu_root: str | None = None):
    """M13 — Quick dependency summary."""
    try:
        from engines.dependency_detector import dependency_summary
        return dependency_summary(emu_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M14 Snapshot Verification
# ---------------------------------------------------------------------------

@app.post("/api/snapshots/capture")
async def api_snapshots_capture(request: Request):
    """M14 — Capture a directory snapshot."""
    try:
        body = await request.json()
        from engines.snapshot_verify import capture_snapshot
        snap = capture_snapshot(
            body["target_path"],
            name=body.get("name"),
            snapshot_type=body.get("snapshot_type", "manual"),
            compute_hashes=body.get("compute_hashes", True),
            related_update_id=body.get("related_update_id"),
        )
        hub = _get_event_hub()
        hub.emit("snapshot.captured", snap.to_dict())
        return snap.to_dict()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/snapshots/compare")
async def api_snapshots_compare(request: Request):
    """M14 — Compare two snapshots."""
    try:
        body = await request.json()
        from engines.snapshot_verify import compare_snapshots
        diff = compare_snapshots(body["pre_name"], body["post_name"])
        return diff.to_dict()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/snapshots/verify")
async def api_snapshots_verify(request: Request):
    """M14 — Verify an update by comparing pre/post snapshots."""
    try:
        body = await request.json()
        from engines.snapshot_verify import verify_update
        return verify_update(
            body["target_path"], body["pre_name"],
            expected_changes=body.get("expected_changes"),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/snapshots/list")
async def api_snapshots_list(snapshot_type: str | None = None, limit: int = 50):
    """M14 — List recorded snapshots."""
    try:
        from engines.snapshot_verify import list_snapshots
        return {"snapshots": list_snapshots(snapshot_type=snapshot_type, limit=limit)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/snapshots/summary")
async def api_snapshots_summary():
    """M14 — Snapshot system summary."""
    try:
        from engines.snapshot_verify import snapshot_summary
        return snapshot_summary()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M15 Automated Rollback on Failure
# ---------------------------------------------------------------------------

@app.post("/api/rollback/check")
async def api_rollback_check(request: Request):
    """M15 — Run post-update health checks for an emulator."""
    try:
        body = await request.json()
        from engines.auto_rollback import run_health_checks
        return run_health_checks(
            body["emulator_name"],
            test_cmd=body.get("test_cmd"),
            emu_root=body.get("emu_root"),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/rollback/trigger")
async def api_rollback_trigger(request: Request):
    """M15 — Trigger an automated rollback."""
    try:
        body = await request.json()
        from engines.auto_rollback import auto_rollback
        result = auto_rollback(
            body["emulator_name"],
            body.get("trigger_reason", "dashboard"),
            update_id=body.get("update_id"),
            backup_path=body.get("backup_path"),
            emu_root=body.get("emu_root"),
        )
        hub = _get_event_hub()
        hub.emit("rollback.completed", result)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/rollback/post-update")
async def api_rollback_post_update(request: Request):
    """M15 — Post-update check: verify health and auto-rollback if needed."""
    try:
        body = await request.json()
        from engines.auto_rollback import post_update_check
        result = post_update_check(
            body["emulator_name"],
            update_id=body.get("update_id"),
            test_cmd=body.get("test_cmd"),
            emu_root=body.get("emu_root"),
        )
        if result.get("action") == "auto_rollback":
            hub = _get_event_hub()
            hub.emit("rollback.auto_triggered", result)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/rollback/policy")
async def api_rollback_policy_set(request: Request):
    """M15 — Set or update rollback policy for an emulator."""
    try:
        body = await request.json()
        from engines.auto_rollback import set_policy
        return set_policy(
            body["emulator_name"],
            auto_rollback_enabled=body.get("auto_rollback_enabled", True),
            health_check_required=body.get("health_check_required", True),
            test_cmd=body.get("test_cmd", ""),
            max_rollback_age_hours=body.get("max_rollback_age_hours", 72),
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rollback/policy/{emulator_name}")
async def api_rollback_policy_get(emulator_name: str):
    """M15 — Get rollback policy for an emulator."""
    try:
        from engines.auto_rollback import get_policy
        return get_policy(emulator_name)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rollback/list")
async def api_rollback_list(emulator_name: str | None = None, limit: int = 20):
    """M15 — List rollback history."""
    try:
        from engines.auto_rollback import list_rollbacks
        return {"rollbacks": list_rollbacks(emulator_name=emulator_name, limit=limit)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rollback/summary")
async def api_rollback_summary():
    """M15 — Rollback system summary."""
    try:
        from engines.auto_rollback import rollback_summary
        return rollback_summary()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M17 AI Natural Language Query
# ---------------------------------------------------------------------------

@app.post("/api/ai/query")
async def api_ai_query(request: Request):
    """M17 — Ask a natural-language question about the collection."""
    try:
        body = await request.json()
        from engines.nl_query import nl_query
        result = nl_query(body["question"], provider=body.get("provider"))
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/ai/recommend")
async def api_ai_recommend(task: str = "agentic", provider: str = "any"):
    """M17 — Recommend the best local LLM model for a task."""
    try:
        from engines.nl_query import recommend_model_for_task
        return recommend_model_for_task(task, provider)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/ai/report")
async def api_ai_report():
    """M17 — Generate comprehensive AI/LLM status report."""
    try:
        from engines.nl_query import full_ai_report
        return full_ai_report()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M22 Event Hub
# ---------------------------------------------------------------------------

@app.get("/api/events/recent")
async def api_events_recent(limit: int = 50, event_type: str | None = None):
    """M22 — Get recent events from the real-time event hub."""
    hub = _get_event_hub()
    events = hub.recent(limit=limit, event_type=event_type)
    return {"events": events, "count": len(events), "clients": hub.client_count}


@app.post("/api/events/emit")
async def api_events_emit(request: Request):
    """M22 — Emit a custom event to all connected WebSocket clients."""
    try:
        body = await request.json()
        hub = _get_event_hub()
        hub.emit(body["event_type"], body.get("data", {}))
        return {"emitted": True, "event": body["event_type"], "clients": hub.client_count}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/events/clients")
async def api_events_clients():
    """M22 — Get count of connected WebSocket clients."""
    hub = _get_event_hub()
    return {"clients": hub.client_count}


# ---------------------------------------------------------------------------
# API — M59 RocketLauncher Media Manager
# ---------------------------------------------------------------------------

@app.get("/api/rl/media/coverage")
async def api_rl_media_coverage(rl_root: str | None = None):
    """M59 — Full RL media coverage report across all systems."""
    try:
        from engines.rl_media_manager import media_coverage
        return media_coverage(rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/media/system/{system}")
async def api_rl_media_system(system: str, rl_root: str | None = None):
    """M59 — Detailed media report for a single system."""
    try:
        from engines.rl_media_manager import system_media_detail
        return system_media_detail(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/media/missing/{system}")
async def api_rl_media_missing(system: str, media_type: str = "all",
                                rl_root: str | None = None):
    """M59 — Find games missing fade, bezel, or pause media."""
    try:
        from engines.rl_media_manager import find_missing_media
        return find_missing_media(system, media_type, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/media/fade/{system}")
async def api_rl_scan_fade(system: str, rl_root: str | None = None):
    """M59 — Scan fade images for a system."""
    try:
        from engines.rl_media_manager import scan_fade
        return scan_fade(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/media/bezels/{system}")
async def api_rl_scan_bezels(system: str, rl_root: str | None = None):
    """M59 — Scan bezel overlays for a system."""
    try:
        from engines.rl_media_manager import scan_bezels
        return scan_bezels(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/media/pause/{system}")
async def api_rl_scan_pause(system: str, rl_root: str | None = None):
    """M59 — Scan pause screen assets for a system."""
    try:
        from engines.rl_media_manager import scan_pause
        return scan_pause(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M60 RocketLauncher Stats, Keymapper & 7z
# ---------------------------------------------------------------------------

@app.get("/api/rl/stats/{system}")
async def api_rl_stats_system(system: str, rl_root: str | None = None):
    """M60 — Parse play statistics for a system."""
    try:
        from engines.rl_stats_keymapper import parse_system_stats
        return parse_system_stats(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/most-played")
async def api_rl_most_played(top_n: int = 25, rl_root: str | None = None):
    """M60 — Most-played games leaderboard."""
    try:
        from engines.rl_stats_keymapper import most_played
        return most_played(rl_root, top_n)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/keymappers")
async def api_rl_keymappers(rl_root: str | None = None):
    """M60 — Scan all keymapper profiles."""
    try:
        from engines.rl_stats_keymapper import scan_keymappers
        return scan_keymappers(rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/multigame/{system}")
async def api_rl_multigame(system: str, rl_root: str | None = None):
    """M60 — Validate MultiGame settings for a system."""
    try:
        from engines.rl_stats_keymapper import validate_multigame
        return validate_multigame(system, rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/7z-settings")
async def api_rl_7z_settings(rl_root: str | None = None):
    """M60 — Check 7z extraction settings."""
    try:
        from engines.rl_stats_keymapper import check_7z_settings
        return check_7z_settings(rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/rl/integration-report")
async def api_rl_integration_report(rl_root: str | None = None):
    """M60 — Full RocketLauncher integration report."""
    try:
        from engines.rl_stats_keymapper import rl_integration_report
        return rl_integration_report(rl_root)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---------------------------------------------------------------------------
# API — M63 Self-Healing Diagnostics & Repair
# ---------------------------------------------------------------------------

@app.post("/api/heal/diagnostics")
async def api_heal_diagnostics():
    """M63 — Run granular self-healing diagnostics, returning per-category results."""
    try:
        from engines.self_healer import run_diagnostics, get_issue_summary
        report = run_diagnostics()
        summary = get_issue_summary(report)
        # Map internal categories to UI categories
        category_map = {
            "config": "config",
            "path": "paths",
            "settings": "config",
            "bios": "bios",
            "permission": "perms",
            "internal": "config",
        }
        ui_categories = {"config": [], "paths": [], "bios": [], "perms": [], "xml": []}
        for issue in report.issues:
            ui_cat = category_map.get(issue.category, "config")
            # XML-related issues go to xml category
            if "xml" in issue.id.lower() or "database" in issue.id.lower() or "db" in issue.description.lower():
                ui_cat = "xml"
            ui_categories[ui_cat].append(issue.to_dict())
        # Build per-category status
        results = {}
        for cat, issues in ui_categories.items():
            errors = [i for i in issues if i["severity"] == "error"]
            warnings = [i for i in issues if i["severity"] == "warn"]
            if errors:
                results[cat] = {"status": "error", "count": len(issues), "errors": len(errors), "warnings": len(warnings), "issues": issues}
            elif warnings:
                results[cat] = {"status": "warn", "count": len(issues), "errors": 0, "warnings": len(warnings), "issues": issues}
            else:
                results[cat] = {"status": "ok", "count": len(issues), "errors": 0, "warnings": 0, "issues": issues}
        return {
            "scan_time": report.scan_time,
            "total_issues": report.total_issues,
            "categories": results,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/heal/repair")
async def api_heal_repair(request: Request):
    """M63 — Run self-healing repairs (dry_run by default)."""
    try:
        body = await request.json()
        from engines.self_healer import heal
        report = heal(
            dry_run=body.get("dry_run", True),
            categories=body.get("categories"),
            max_repairs=body.get("max_repairs", 50),
        )
        hub = _get_event_hub()
        hub.emit("heal.completed", {"dry_run": report.dry_run, "success": report.total_success, "failed": report.total_failed})
        return report.to_dict()
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
