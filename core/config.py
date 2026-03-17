"""Configuration loader and validator for the HyperSpin Extreme Toolkit."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG = "config.yaml"
_config_cache: dict[str, Any] | None = None

# Toolkit root (same level as config.yaml)
_TOOLKIT_ROOT = Path(__file__).resolve().parent.parent
_DRIVES_STATE  = _TOOLKIT_ROOT / "drives.json"


# ── Drive state helpers ───────────────────────────────────────────────

def _load_drives_state() -> dict:
    """Load drives.json for {primary}/{secondary}/{tertiary} resolution."""
    if _DRIVES_STATE.exists():
        try:
            return json.loads(_DRIVES_STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _resolve_drive_tokens(obj: Any, drive_vars: dict[str, str]) -> None:
    """Recursively replace {primary}, {secondary}, {tertiary}, {*_root} tokens."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, str):
                for token, replacement in drive_vars.items():
                    val = val.replace(token, replacement)
                obj[key] = val
            else:
                _resolve_drive_tokens(val, drive_vars)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            if isinstance(val, str):
                for token, replacement in drive_vars.items():
                    val = val.replace(token, replacement)
                obj[i] = val
            else:
                _resolve_drive_tokens(val, drive_vars)


def _build_drive_vars(cfg: dict[str, Any]) -> dict[str, str]:
    """
    Build the token→value substitution map from drives.json and config.yaml drives section.

    Priority: drives.json (live selection) > config.yaml drives: section > fallback
    """
    drives_json = _load_drives_state()
    drives_cfg  = cfg.get("drives", {})
    fallback    = drives_cfg.get("fallback_letter", "D")

    # Resolve primary letter
    primary = (
        drives_json.get("primary")
        or drives_cfg.get("primary")
        or _auto_detect_primary(drives_cfg)
        or fallback
    )
    primary = str(primary).upper().strip(":\\")

    secondary = (
        drives_json.get("secondary")
        or drives_cfg.get("secondary")
        or primary
    )
    secondary = str(secondary).upper().strip(":\\")

    tertiary = (
        drives_json.get("tertiary")
        or drives_cfg.get("tertiary")
        or secondary
    )
    tertiary = str(tertiary).upper().strip(":\\")

    # Resolve root subfolder names
    arc_root = (
        drives_json.get("arcade_root")
        or drives_cfg.get("arcade_root", "Arcade")
    )
    sec_root = (
        drives_json.get("secondary_root")
        or drives_cfg.get("secondary_root", "Arcade")
    )
    ter_root = (
        drives_json.get("tertiary_root")
        or drives_cfg.get("tertiary_root", "Arcade")
    )

    return {
        "{toolkit_root}":   str(_TOOLKIT_ROOT),
        "{primary}":        primary,
        "{secondary}":      secondary,
        "{tertiary}":       tertiary,
        "{primary_root}":   f"{primary}:\\{arc_root}",
        "{secondary_root}": f"{secondary}:\\{sec_root}",
        "{tertiary_root}":  f"{tertiary}:\\{ter_root}",
    }


def _auto_detect_primary(drives_cfg: dict) -> str | None:
    """
    Quick auto-detect: scan drives for arcade content.
    Only runs if drives.json is absent and config.yaml has no primary set.
    Returns drive letter or None.
    """
    try:
        import string
        arcade_root = drives_cfg.get("arcade_root", "Arcade")
        system_drive = os.environ.get("SystemDrive", "C:")[0].upper()
        fingerprints = ["HyperSpin", "emulators", "ROMs", "RocketLauncher", arcade_root]
        min_gb = float(drives_cfg.get("min_game_drive_gb", 500))

        for letter in string.ascii_uppercase:
            if letter == system_drive:
                continue
            drive = f"{letter}:\\"
            if not os.path.exists(drive):
                continue
            # Quick size check
            try:
                import shutil
                usage = shutil.disk_usage(drive)
                if usage.total / (1024**3) < min_gb:
                    continue
            except Exception:
                continue
            # Check for any fingerprint
            for fp in fingerprints:
                if Path(drive, fp).exists() or Path(drive, arcade_root, fp).exists():
                    return letter
    except Exception:
        pass
    return None


# ── Config loader ─────────────────────────────────────────────────────

def _find_config_path() -> Path:
    """Locate config.yaml relative to the toolkit root."""
    candidate = _TOOLKIT_ROOT / _DEFAULT_CONFIG
    if candidate.exists():
        return candidate
    env = os.environ.get("HSTK_CONFIG")
    if env and Path(env).exists():
        return Path(env)
    print(f"[FATAL] config.yaml not found at {candidate}", file=sys.stderr)
    sys.exit(1)


_reconcile_done = False  # prevent infinite recursion (reconcile reads drives.json)


def _reconcile_drives_if_needed() -> None:
    """Run the smart drive index reconciliation once per process.

    This detects letter changes, discovers new drives, and auto-heals
    role assignments BEFORE config tokens are resolved.
    """
    global _reconcile_done
    if _reconcile_done:
        return
    _reconcile_done = True
    try:
        from engines.drive_index import reconcile
        reconcile(detect_type=False)
    except Exception:
        pass  # non-fatal — drives.json may not exist yet on first run


def load_config(path: Path | str | None = None, *, reload: bool = False) -> dict[str, Any]:
    """Load and cache the YAML configuration."""
    global _config_cache
    if _config_cache is not None and not reload:
        return _config_cache

    cfg_path = Path(path) if path else _find_config_path()
    with open(cfg_path, "r", encoding="utf-8") as fh:
        _config_cache = yaml.safe_load(fh) or {}

    # 0. Reconcile drive index (detect letter changes, new drives)
    _reconcile_drives_if_needed()
    # 1. Expand %ENV_VARS%
    _expand_env_vars(_config_cache)
    # 2. Resolve {primary}/{secondary}/{tertiary} drive tokens
    drive_vars = _build_drive_vars(_config_cache)
    _resolve_drive_tokens(_config_cache, drive_vars)
    # 3. Ensure toolkit-owned dirs exist
    _ensure_dirs(_config_cache)
    return _config_cache


def reload_config() -> dict[str, Any]:
    """Force a fresh config reload (e.g. after drives change)."""
    global _config_cache
    _config_cache = None
    return load_config()


def _expand_env_vars(obj: Any) -> None:
    """Recursively expand %VAR% and $VAR in string values."""
    if isinstance(obj, dict):
        for key, val in obj.items():
            if isinstance(val, str):
                obj[key] = os.path.expandvars(val)
            else:
                _expand_env_vars(val)
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            if isinstance(val, str):
                obj[i] = os.path.expandvars(val)
            else:
                _expand_env_vars(val)


def _ensure_dirs(cfg: dict[str, Any]) -> None:
    """Create toolkit-owned directories if they don't exist."""
    paths = cfg.get("paths", {})
    for key in ("data_dir", "logs_dir", "backup_root", "recovery_root", "output_root"):
        d = paths.get(key)
        if d:
            try:
                Path(d).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    updates = cfg.get("updates", {})
    q = updates.get("quarantine_dir")
    if q:
        try:
            Path(q).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


def get(key_path: str, default: Any = None) -> Any:
    """Dot-notation config access: get('ai.ollama.base_url')."""
    cfg = load_config()
    parts = key_path.split(".")
    node: Any = cfg
    for part in parts:
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


def get_drive_vars() -> dict[str, str]:
    """Return the current drive token substitution map."""
    cfg = load_config()
    return _build_drive_vars(cfg)
