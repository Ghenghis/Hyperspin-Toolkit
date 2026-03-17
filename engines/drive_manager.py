"""Drive Manager — backward-compatible wrapper around drive_index.py.

All logic now lives in ``engines.drive_index`` which uses a fingerprint-based
smart drive identity system.  This file re-exports every public symbol so
existing ``from engines.drive_manager import ...`` statements keep working.
"""
from __future__ import annotations

from engines.drive_index import (          # noqa: F401  — re-exports
    TOOLKIT_ROOT,
    INDEX_FILE as DRIVES_STATE,
    ARCADE_FINGERPRINTS,
    ARCADE_ROOT_NAMES,
    MIN_GAME_DRIVE_GB,
    # State helpers (backward-compat names)
    load_state,
    save_state,
    load_index,
    save_index,
    # Scanning
    scan_drives,
    auto_assign,
    reconcile,
    # Path helpers
    resolve_path,
    get_primary_root,
    get_secondary_root,
    get_tertiary_root,
    # Status / query
    drive_status,
    list_indexed_drives,
    get_drive_for_role,
    assign_role,
    # Internal helpers consumers may use
    _get_all_drives,
    _drive_usage,
    _detect_arcade_content,
    _detect_drive_type,
    _get_volume_serial,
    _get_volume_label,
    _content_hash,
    _make_fingerprint,
    _human_gb,
)

DEFAULT_STATE: dict = {
    "version": 2,
    "primary":   None,
    "secondary": None,
    "tertiary":  None,
    "arcade_root": "Arcade",
    "secondary_root": "Arcade",
    "tertiary_root":  "Arcade",
    "last_scan": None,
}


if __name__ == "__main__":
    from engines.drive_index import _mcp_main
    _mcp_main()
