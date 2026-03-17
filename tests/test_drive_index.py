"""Tests for engines.drive_index — Smart fingerprint-based drive indexing.

Covers:
  - Fingerprint generation (_make_fingerprint, _content_hash)
  - Index lifecycle (load, save, migrate v1→v2)
  - Reconcile: letter-change detection, new-drive discovery, disconnection tracking
  - Role assignment (assign_role, _auto_fill_roles)
  - Legacy backward-compatibility (load_state, save_state, _sync_legacy_keys)
  - Path resolution (resolve_path, get_primary_root)
  - drive_status / list_indexed_drives queries
"""
from __future__ import annotations

import datetime
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# ── Helpers ───────────────────────────────────────────────────────────

FAKE_NOW = "2025-01-15T12:00:00"


def _patch_toolkit_root(tmp_path):
    """Patch TOOLKIT_ROOT and INDEX_FILE to a temp directory."""
    return [
        mock.patch("engines.drive_index.TOOLKIT_ROOT", tmp_path),
        mock.patch("engines.drive_index.INDEX_FILE", tmp_path / "drives.json"),
    ]


def _write_index(tmp_path, data: dict):
    (tmp_path / "drives.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_index(tmp_path) -> dict:
    return json.loads((tmp_path / "drives.json").read_text(encoding="utf-8"))


def _sample_index(primary_letter="D", primary_fp="fp_aaa111bbb2"):
    """Build a minimal valid v2 index for testing."""
    return {
        "version": 2,
        "drives": {
            primary_fp: {
                "fingerprint": primary_fp,
                "volume_serial": "1234-ABCD",
                "content_hash": "abcdef1234567890",
                "label": "ARCADE_DRIVE",
                "current_letter": primary_letter,
                "last_letter": primary_letter,
                "arcade_root": "Arcade",
                "content_types": ["Arcade\\HyperSpin", "Arcade\\ROMs"],
                "confidence": 30,
                "drive_type": "SSD",
                "role": "primary",
                "connected": True,
                "is_system": False,
                "first_seen": "2025-01-01T00:00:00",
                "last_seen": "2025-01-10T00:00:00",
                "total_gb": 1000.0,
                "used_gb": 500.0,
                "free_gb": 500.0,
                "total_human": "1.0 TB",
                "used_human": "500.0 GB",
                "free_human": "500.0 GB",
                "used_pct": 50.0,
            },
        },
        "roles": {"primary": primary_fp, "secondary": None, "tertiary": None},
        "last_scan": "2025-01-10T00:00:00",
        "primary": primary_letter,
        "secondary": None,
        "tertiary": None,
        "arcade_root": "Arcade",
        "secondary_root": "Arcade",
        "tertiary_root": "Arcade",
    }


# =====================================================================
# Fingerprint helpers
# =====================================================================

class TestFingerprinting:
    def test_make_fingerprint_deterministic(self):
        from engines.drive_index import _make_fingerprint
        fp1 = _make_fingerprint("1234-ABCD", "content123")
        fp2 = _make_fingerprint("1234-ABCD", "content123")
        assert fp1 == fp2
        assert len(fp1) == 12

    def test_make_fingerprint_different_serial(self):
        from engines.drive_index import _make_fingerprint
        fp1 = _make_fingerprint("1234-ABCD", "content123")
        fp2 = _make_fingerprint("5678-EFGH", "content123")
        assert fp1 != fp2

    def test_make_fingerprint_no_serial(self):
        from engines.drive_index import _make_fingerprint
        fp = _make_fingerprint(None, "content123")
        assert len(fp) == 12
        # Should still produce a consistent hash
        assert fp == _make_fingerprint(None, "content123")

    def test_content_hash_returns_hex_string(self):
        """_content_hash should produce a hex digest even for non-existent drives."""
        from engines.drive_index import _content_hash
        with mock.patch("pathlib.Path.iterdir", return_value=[]):
            result = _content_hash("Z")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_content_hash_sorts_directory_names(self):
        from engines.drive_index import _content_hash
        fake_dirs = [
            mock.Mock(name="ROMs", is_dir=mock.Mock(return_value=True)),
            mock.Mock(name="Arcade", is_dir=mock.Mock(return_value=True)),
        ]
        # Set .name explicitly (Mock(name=...) sets internal name, not attribute)
        fake_dirs[0].name = "ROMs"
        fake_dirs[1].name = "Arcade"

        with mock.patch("pathlib.Path.iterdir", return_value=iter(fake_dirs)):
            h1 = _content_hash("Z")

        fake_dirs_reversed = list(reversed(fake_dirs))
        with mock.patch("pathlib.Path.iterdir", return_value=iter(fake_dirs_reversed)):
            h2 = _content_hash("Z")

        assert h1 == h2, "Content hash should be order-independent"


# =====================================================================
# Index lifecycle
# =====================================================================

class TestIndexLifecycle:
    def test_load_empty_index(self, tmp_path):
        """Loading when no drives.json exists returns empty v2 index."""
        from engines.drive_index import load_index
        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()
        try:
            idx = load_index()
            assert idx["version"] == 2
            assert idx["drives"] == {}
            assert idx["roles"]["primary"] is None
        finally:
            for p in patches:
                p.stop()

    def test_save_and_reload(self, tmp_path):
        from engines.drive_index import save_index, load_index
        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()
        try:
            idx = _sample_index()
            save_index(idx)
            reloaded = load_index()
            assert reloaded["version"] == 2
            assert "fp_aaa111bbb2" in reloaded["drives"]
            assert reloaded["primary"] == "D"
        finally:
            for p in patches:
                p.stop()

    def test_migrate_v1_to_v2(self, tmp_path):
        """Legacy v1 drives.json (flat letter-based) should be migrated."""
        from engines.drive_index import load_index
        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()

        v1_data = {
            "primary": "D",
            "secondary": None,
            "tertiary": None,
            "arcade_root": "Arcade",
            "secondary_root": "Arcade",
            "tertiary_root": "Arcade",
            "last_scan": "2025-01-01T00:00:00",
        }
        _write_index(tmp_path, v1_data)

        with mock.patch("engines.drive_index._get_volume_serial", return_value="1234-ABCD"), \
             mock.patch("engines.drive_index._content_hash", return_value="abcdef1234567890"), \
             mock.patch("engines.drive_index._get_volume_label", return_value="GAMES"), \
             mock.patch("engines.drive_index._detect_arcade_content", return_value={
                 "found": True, "arcade_root": "Arcade",
                 "content_types": ["Arcade"], "confidence": 10,
             }), \
             mock.patch("os.path.exists", return_value=True):
            try:
                idx = load_index()
                assert idx["version"] == 2
                assert len(idx["drives"]) == 1
                fp = list(idx["drives"].keys())[0]
                assert idx["roles"]["primary"] == fp
                assert idx["drives"][fp]["current_letter"] == "D"
            finally:
                for p in patches:
                    p.stop()


# =====================================================================
# Reconciliation — the heart of the system
# =====================================================================

class TestReconcile:
    def _mock_scan_results(self, drives_info):
        """Build scan results matching the format of scan_drives()."""
        results = []
        for d in drives_info:
            results.append({
                "letter": d["letter"],
                "label": d.get("label", ""),
                "fingerprint": d.get("fingerprint", ""),
                "volume_serial": d.get("serial", ""),
                "content_hash": d.get("chash", ""),
                "is_system": d.get("is_system", False),
                "is_arcade": d.get("is_arcade", False),
                "arcade_root": d.get("arcade_root", "Arcade"),
                "content_types": d.get("content_types", []),
                "confidence": d.get("confidence", 0),
                "total_gb": d.get("total_gb", 1000),
                "used_gb": 500, "free_gb": 500,
                "total_human": "1.0 TB", "used_human": "500.0 GB",
                "free_human": "500.0 GB", "used_pct": 50.0,
            })
        return results

    def test_reconcile_detects_letter_change(self, tmp_path):
        """When a known drive shows up on a different letter, detect the change."""
        from engines.drive_index import reconcile, load_index

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()

        idx = _sample_index(primary_letter="D", primary_fp="fp_aaa111bbb2")
        _write_index(tmp_path, idx)

        # Simulate drive D now appearing as E (same serial)
        scan_results = self._mock_scan_results([
            {"letter": "C", "serial": "SYS-0000", "chash": "sys_hash",
             "is_system": True, "label": "Windows"},
            {"letter": "E", "serial": "1234-ABCD", "chash": "abcdef1234567890",
             "is_arcade": True, "arcade_root": "Arcade",
             "content_types": ["Arcade\\HyperSpin"], "confidence": 30,
             "label": "ARCADE_DRIVE"},
        ])

        with mock.patch("engines.drive_index.scan_drives", return_value=scan_results), \
             mock.patch("engines.drive_index._detect_arcade_content", return_value={
                 "found": True, "arcade_root": "Arcade",
                 "content_types": ["Arcade"], "confidence": 30,
             }):
            try:
                result = reconcile(detect_type=False)

                events = result.get("events", [])
                letter_changes = [e for e in events if e["type"] == "letter_changed"]
                assert len(letter_changes) == 1
                assert letter_changes[0]["old_letter"] == "D"
                assert letter_changes[0]["new_letter"] == "E"

                # Legacy key should now point to E
                assert result["primary"] == "E"
            finally:
                for p in patches:
                    p.stop()

    def test_reconcile_discovers_new_drive(self, tmp_path):
        """A drive not in the index with arcade content should be discovered."""
        from engines.drive_index import reconcile

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()

        idx = _sample_index()
        _write_index(tmp_path, idx)

        scan_results = self._mock_scan_results([
            {"letter": "D", "serial": "1234-ABCD", "chash": "abcdef1234567890",
             "is_arcade": True, "confidence": 30, "label": "ARCADE_DRIVE"},
            {"letter": "F", "serial": "NEW-SERIAL", "chash": "new_content_hash",
             "is_arcade": True, "arcade_root": "Games",
             "content_types": ["Games\\ROMs"], "confidence": 20,
             "label": "NEW_DRIVE"},
        ])

        with mock.patch("engines.drive_index.scan_drives", return_value=scan_results), \
             mock.patch("engines.drive_index._detect_arcade_content", return_value={
                 "found": True, "arcade_root": "Games",
                 "content_types": ["Games\\ROMs"], "confidence": 20,
             }), \
             mock.patch("engines.drive_index._make_fingerprint", side_effect=lambda s, c: f"fp_{s[:4]}"):
            try:
                result = reconcile(detect_type=False)

                events = result.get("events", [])
                new_drives = [e for e in events if e["type"] == "new_arcade_drive"]
                assert len(new_drives) == 1
                assert new_drives[0]["letter"] == "F"
                assert len(result["drives"]) >= 2
            finally:
                for p in patches:
                    p.stop()

    def test_reconcile_marks_disconnected(self, tmp_path):
        """Drives in index but not in scan should be marked disconnected."""
        from engines.drive_index import reconcile

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()

        idx = _sample_index()
        _write_index(tmp_path, idx)

        # Scan returns empty — primary drive is gone
        scan_results = self._mock_scan_results([
            {"letter": "C", "serial": "SYS-0000", "chash": "sys_hash",
             "is_system": True, "label": "Windows"},
        ])

        with mock.patch("engines.drive_index.scan_drives", return_value=scan_results):
            try:
                result = reconcile(detect_type=False)

                events = result.get("events", [])
                offline = [e for e in events if e["type"] == "role_drive_offline"]
                assert len(offline) >= 1
                assert offline[0]["role"] == "primary"

                drv = result["drives"]["fp_aaa111bbb2"]
                assert drv["connected"] is False
            finally:
                for p in patches:
                    p.stop()

    def test_reconcile_auto_assigns_roles(self, tmp_path):
        """Unassigned roles should be filled from available arcade drives."""
        from engines.drive_index import reconcile

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()

        # Start with empty index
        _write_index(tmp_path, {
            "version": 2,
            "drives": {},
            "roles": {"primary": None, "secondary": None, "tertiary": None},
            "last_scan": None,
            "primary": None, "secondary": None, "tertiary": None,
            "arcade_root": "Arcade", "secondary_root": "Arcade", "tertiary_root": "Arcade",
        })

        scan_results = self._mock_scan_results([
            {"letter": "C", "serial": "SYS", "chash": "sys", "is_system": True},
            {"letter": "D", "serial": "AAA", "chash": "d_hash",
             "is_arcade": True, "confidence": 50, "label": "Big Drive",
             "total_gb": 2000},
            {"letter": "E", "serial": "BBB", "chash": "e_hash",
             "is_arcade": True, "confidence": 20, "label": "Small Drive",
             "total_gb": 500},
        ])

        with mock.patch("engines.drive_index.scan_drives", return_value=scan_results), \
             mock.patch("engines.drive_index._detect_arcade_content", return_value={
                 "found": True, "arcade_root": "Arcade",
                 "content_types": ["Arcade"], "confidence": 30,
             }):
            try:
                result = reconcile(detect_type=False)

                # Primary should be assigned (highest confidence)
                assert result["primary"] is not None
                assert result["roles"]["primary"] is not None
            finally:
                for p in patches:
                    p.stop()


# =====================================================================
# Role assignment
# =====================================================================

class TestRoleAssignment:
    def test_assign_role_creates_drive_record(self, tmp_path):
        from engines.drive_index import assign_role, load_index

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()
        try:
            # Start with empty index
            idx = assign_role(
                "primary", "D", "Arcade",
                idx={
                    "version": 2, "drives": {},
                    "roles": {"primary": None, "secondary": None, "tertiary": None},
                    "last_scan": None,
                    "primary": None, "secondary": None, "tertiary": None,
                    "arcade_root": "Arcade", "secondary_root": "Arcade", "tertiary_root": "Arcade",
                },
            )
            # Should have created a drive record and assigned the role
            assert idx["roles"]["primary"] is not None
            fp = idx["roles"]["primary"]
            assert fp in idx["drives"]
            assert idx["drives"][fp]["role"] == "primary"
            assert idx["primary"] == "D"
        finally:
            for p in patches:
                p.stop()

    @mock.patch("engines.drive_index._get_volume_serial", return_value="1234-ABCD")
    @mock.patch("engines.drive_index._content_hash", return_value="test_hash_123456")
    @mock.patch("engines.drive_index._get_volume_label", return_value="TEST")
    @mock.patch("engines.drive_index._detect_arcade_content", return_value={
        "found": True, "arcade_root": "Arcade", "content_types": [], "confidence": 10,
    })
    @mock.patch("os.path.exists", return_value=True)
    def test_assign_role_rejects_invalid_role(self, *mocks):
        from engines.drive_index import assign_role, _empty_index
        with pytest.raises(ValueError, match="Unknown role"):
            assign_role("quaternary", "D", "Arcade", idx=_empty_index())

    @mock.patch("os.path.exists", return_value=False)
    def test_assign_role_rejects_missing_drive(self, _):
        from engines.drive_index import assign_role, _empty_index
        with pytest.raises(FileNotFoundError):
            assign_role("primary", "Z", "Arcade", idx=_empty_index())


# =====================================================================
# Backward compatibility
# =====================================================================

class TestBackwardCompat:
    def test_load_state_returns_legacy_keys(self, tmp_path):
        from engines.drive_index import load_state

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()
        try:
            _write_index(tmp_path, _sample_index())
            state = load_state()
            assert state["primary"] == "D"
            assert state["arcade_root"] == "Arcade"
            assert "version" in state
        finally:
            for p in patches:
                p.stop()

    def test_sync_legacy_keys(self):
        from engines.drive_index import _sync_legacy_keys

        idx = _sample_index(primary_letter="E", primary_fp="fp_test123456")
        idx["drives"]["fp_test123456"]["current_letter"] = "G"
        idx["drives"]["fp_test123456"]["arcade_root"] = "Games"
        _sync_legacy_keys(idx)
        assert idx["primary"] == "G"
        assert idx["arcade_root"] == "Games"

    def test_save_state_calls_save_index(self, tmp_path):
        from engines.drive_index import save_state

        patches = _patch_toolkit_root(tmp_path)
        for p in patches:
            p.start()
        try:
            idx = _sample_index()
            save_state(idx)
            assert (tmp_path / "drives.json").exists()
            data = _read_index(tmp_path)
            assert data["version"] == 2
        finally:
            for p in patches:
                p.stop()


# =====================================================================
# Path resolution
# =====================================================================

class TestPathResolution:
    def test_resolve_path_basic(self):
        from engines.drive_index import resolve_path
        idx = _sample_index()
        result = resolve_path("{primary}:\\Arcade\\ROMs", state=idx)
        assert result == "D:\\Arcade\\ROMs"

    def test_resolve_path_root_token(self):
        from engines.drive_index import resolve_path
        idx = _sample_index()
        result = resolve_path("{primary_root}", state=idx)
        assert result == "D:\\Arcade"

    def test_resolve_path_secondary_fallback(self):
        from engines.drive_index import resolve_path
        idx = _sample_index()
        # secondary is None → falls back to primary
        result = resolve_path("{secondary}:\\stuff", state=idx)
        assert result == "D:\\stuff"

    def test_get_primary_root(self):
        from engines.drive_index import get_primary_root
        idx = _sample_index()
        root = get_primary_root(state=idx)
        assert str(root) == "D:\\Arcade"

    def test_get_secondary_root_none(self):
        from engines.drive_index import get_secondary_root
        idx = _sample_index()
        root = get_secondary_root(state=idx)
        assert root is None


# =====================================================================
# Query functions
# =====================================================================

class TestQueryFunctions:
    def test_drive_status_shows_role_info(self, tmp_path):
        from engines.drive_index import drive_status

        idx = _sample_index()
        with mock.patch("engines.drive_index._drive_usage", return_value={
            "total_gb": 1000, "used_gb": 500, "free_gb": 500,
            "total_human": "1.0 TB", "used_human": "500.0 GB",
            "free_human": "500.0 GB", "used_pct": 50.0,
        }), mock.patch("os.path.exists", return_value=True), \
             mock.patch("pathlib.Path.exists", return_value=True):
            status = drive_status(state=idx)

        assert status["drives"]["primary"]["assigned"] is True
        assert status["drives"]["primary"]["letter"] == "D"
        assert status["drives"]["primary"]["fingerprint"] == "fp_aaa111bbb2"
        assert status["drives"]["secondary"]["assigned"] is False

    def test_list_indexed_drives(self):
        from engines.drive_index import list_indexed_drives
        idx = _sample_index()
        drives = list_indexed_drives(idx=idx)
        assert len(drives) == 1
        assert drives[0]["fingerprint"] == "fp_aaa111bbb2"
        assert drives[0]["letter"] == "D"
        assert drives[0]["connected"] is True

    def test_get_drive_for_role(self):
        from engines.drive_index import get_drive_for_role
        idx = _sample_index()
        drv = get_drive_for_role("primary", idx=idx)
        assert drv is not None
        assert drv["current_letter"] == "D"

    def test_get_drive_for_unassigned_role(self):
        from engines.drive_index import get_drive_for_role
        idx = _sample_index()
        drv = get_drive_for_role("secondary", idx=idx)
        assert drv is None


# =====================================================================
# drive_manager wrapper backward compat
# =====================================================================

class TestDriveManagerWrapper:
    def test_wrapper_imports(self):
        """All imports from engines.drive_manager should resolve."""
        from engines.drive_manager import (
            TOOLKIT_ROOT, DRIVES_STATE,
            ARCADE_FINGERPRINTS, ARCADE_ROOT_NAMES, MIN_GAME_DRIVE_GB,
            load_state, save_state, load_index, save_index,
            scan_drives, auto_assign, reconcile,
            resolve_path, get_primary_root, get_secondary_root, get_tertiary_root,
            drive_status, list_indexed_drives, get_drive_for_role, assign_role,
            _get_all_drives, _drive_usage, _detect_arcade_content,
            _detect_drive_type, _get_volume_serial, _get_volume_label,
            _content_hash, _make_fingerprint, _human_gb,
            DEFAULT_STATE,
        )
        assert TOOLKIT_ROOT is not None
        assert callable(load_state)
        assert callable(reconcile)
        assert isinstance(DEFAULT_STATE, dict)
        assert DEFAULT_STATE["version"] == 2
