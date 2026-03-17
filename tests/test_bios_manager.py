"""Tests for the BIOS Management & Verification Engine (engines/bios_manager.py).

Covers:
  - MD5 hashing
  - BIOS file search (case-insensitive, multi-path)
  - Single BIOS verification (valid, bad_hash, missing)
  - System-level audit with health scoring
  - Full audit across all known systems
  - Custom DAT loading and merging
  - Utility functions (list_known_systems, get_missing_bios_summary)
"""

import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.bios_manager import (
    KNOWN_BIOS,
    BiosAuditReport,
    BiosEntry,
    BiosFileResult,
    SystemBiosHealth,
    audit_all_bios,
    audit_system_bios,
    get_missing_bios_summary,
    get_system_requirements,
    hash_file_md5,
    list_known_systems,
    load_bios_dat,
    merge_bios_database,
    verify_bios_file,
    _build_search_paths,
    _calc_health_score,
    _classify_health,
    _find_bios_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_bios_dir(tmp_path):
    """Create a mock BIOS directory with sample files."""
    bios_dir = tmp_path / "system"
    bios_dir.mkdir()
    return bios_dir


@pytest.fixture
def sample_bios_file(tmp_bios_dir):
    """Create a sample BIOS file with known content and return (path, md5)."""
    content = b"FAKE_BIOS_CONTENT_FOR_TESTING_12345"
    md5 = hashlib.md5(content).hexdigest()
    bios_file = tmp_bios_dir / "test_bios.bin"
    bios_file.write_bytes(content)
    return bios_file, md5


@pytest.fixture
def ps1_bios_entry():
    """Return a BiosEntry for PS1 USA BIOS."""
    return BiosEntry(
        filename="scph5501.bin",
        md5="490f666e1afb15b7571ff3f97f93b789",
        required=True,
        desc="PS1 BIOS (USA v3.0 11/18/96)",
        system="PlayStation",
    )


# ---------------------------------------------------------------------------
# hash_file_md5
# ---------------------------------------------------------------------------

class TestHashFileMd5:
    def test_hash_known_content(self, tmp_path):
        content = b"hello world"
        expected = hashlib.md5(content).hexdigest()
        f = tmp_path / "test.bin"
        f.write_bytes(content)
        assert hash_file_md5(f) == expected

    def test_hash_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.md5(b"").hexdigest()
        assert hash_file_md5(f) == expected

    def test_hash_nonexistent_file(self, tmp_path):
        f = tmp_path / "nonexistent.bin"
        assert hash_file_md5(f) == ""

    def test_hash_large_file(self, tmp_path):
        """Ensure chunked reading works for files > 1MB."""
        content = b"X" * (2 * 1024 * 1024)  # 2MB
        expected = hashlib.md5(content).hexdigest()
        f = tmp_path / "large.bin"
        f.write_bytes(content)
        assert hash_file_md5(f) == expected


# ---------------------------------------------------------------------------
# _find_bios_file
# ---------------------------------------------------------------------------

class TestFindBiosFile:
    def test_find_direct_match(self, tmp_bios_dir):
        target = tmp_bios_dir / "scph5501.bin"
        target.write_bytes(b"bios")
        result = _find_bios_file("scph5501.bin", [tmp_bios_dir])
        assert result is not None
        assert result.name == "scph5501.bin"

    def test_find_case_insensitive(self, tmp_bios_dir):
        target = tmp_bios_dir / "SCPH5501.BIN"
        target.write_bytes(b"bios")
        result = _find_bios_file("scph5501.bin", [tmp_bios_dir])
        assert result is not None

    def test_find_not_found(self, tmp_bios_dir):
        result = _find_bios_file("nonexistent.bin", [tmp_bios_dir])
        assert result is None

    def test_find_multiple_paths_priority(self, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / "bios.bin").write_bytes(b"first")
        (dir2 / "bios.bin").write_bytes(b"second")
        result = _find_bios_file("bios.bin", [dir1, dir2])
        assert result is not None
        assert str(dir1) in str(result)

    def test_find_empty_search_paths(self):
        result = _find_bios_file("bios.bin", [])
        assert result is None

    def test_find_nonexistent_search_dir(self, tmp_path):
        fake_dir = tmp_path / "nonexistent"
        result = _find_bios_file("bios.bin", [fake_dir])
        assert result is None


# ---------------------------------------------------------------------------
# verify_bios_file
# ---------------------------------------------------------------------------

class TestVerifyBiosFile:
    def test_valid_bios(self, sample_bios_file, tmp_bios_dir):
        bios_path, md5 = sample_bios_file
        entry = BiosEntry(
            filename="test_bios.bin", md5=md5, required=True,
            desc="Test BIOS", system="TestSystem",
        )
        result = verify_bios_file(entry, [tmp_bios_dir])
        assert result.status == "valid"
        assert result.found is True
        assert result.valid is True
        assert result.actual_md5 == md5

    def test_bad_hash_bios(self, tmp_bios_dir):
        (tmp_bios_dir / "wrong.bin").write_bytes(b"wrong content")
        entry = BiosEntry(
            filename="wrong.bin", md5="0000000000000000000000000000dead",
            required=True, desc="Wrong hash test", system="TestSystem",
        )
        result = verify_bios_file(entry, [tmp_bios_dir])
        assert result.status == "bad_hash"
        assert result.found is True
        assert result.valid is False
        assert result.actual_md5 != entry.md5

    def test_missing_bios(self, tmp_bios_dir):
        entry = BiosEntry(
            filename="missing.bin", md5="abcdef1234567890abcdef1234567890",
            required=True, desc="Missing test", system="TestSystem",
        )
        result = verify_bios_file(entry, [tmp_bios_dir])
        assert result.status == "missing"
        assert result.found is False
        assert result.valid is False

    def test_archive_bios_no_hash(self, tmp_bios_dir):
        """Archive BIOS (e.g. neogeo.zip) with no hash — existence is sufficient."""
        (tmp_bios_dir / "neogeo.zip").write_bytes(b"PK\x03\x04fake")
        entry = BiosEntry(
            filename="neogeo.zip", md5="", required=True,
            desc="Neo Geo BIOS", system="Neo Geo",
        )
        result = verify_bios_file(entry, [tmp_bios_dir])
        assert result.status == "valid"
        assert result.found is True
        assert result.valid is True


# ---------------------------------------------------------------------------
# audit_system_bios
# ---------------------------------------------------------------------------

class TestAuditSystemBios:
    def test_all_bios_present_valid(self, tmp_bios_dir):
        # Create two fake BIOS files with known MD5s
        content1 = b"bios_content_one"
        content2 = b"bios_content_two"
        md5_1 = hashlib.md5(content1).hexdigest()
        md5_2 = hashlib.md5(content2).hexdigest()
        (tmp_bios_dir / "req.bin").write_bytes(content1)
        (tmp_bios_dir / "opt.bin").write_bytes(content2)

        entries = [
            BiosEntry("req.bin", md5_1, True, "Required BIOS"),
            BiosEntry("opt.bin", md5_2, False, "Optional BIOS"),
        ]
        health = audit_system_bios("TestSystem", [tmp_bios_dir], bios_entries=entries)
        assert health.status == "healthy"
        assert health.health_score == 100.0
        assert health.found == 2
        assert health.valid == 2
        assert health.missing_required == 0

    def test_missing_required_bios(self, tmp_bios_dir):
        entries = [
            BiosEntry("missing_req.bin", "aaaa" * 8, True, "Required missing"),
        ]
        health = audit_system_bios("TestSystem", [tmp_bios_dir], bios_entries=entries)
        assert health.status == "critical"
        assert health.missing_required == 1
        assert health.health_score < 25  # 20% from optional weight, 0% from required
        assert len(health.issues) >= 1

    def test_bad_hash_degrades(self, tmp_bios_dir):
        content = b"wrong_content"
        (tmp_bios_dir / "bad.bin").write_bytes(content)
        entries = [
            BiosEntry("bad.bin", "0000" * 8, True, "Bad hash BIOS"),
        ]
        health = audit_system_bios("TestSystem", [tmp_bios_dir], bios_entries=entries)
        assert health.status == "degraded"
        assert health.bad_hash == 1
        assert 0 < health.health_score < 100

    def test_empty_system(self, tmp_bios_dir):
        health = audit_system_bios("EmptySystem", [tmp_bios_dir], bios_entries=[])
        assert health.total_bios == 0
        assert health.health_score == 100.0

    def test_known_system_from_database(self, tmp_bios_dir):
        """Audit a real system from KNOWN_BIOS (all will be missing in temp dir)."""
        health = audit_system_bios("PlayStation", [tmp_bios_dir])
        assert health.system == "PlayStation"
        assert health.total_bios > 0
        assert health.missing_required > 0
        assert health.status == "critical"


# ---------------------------------------------------------------------------
# _calc_health_score and _classify_health
# ---------------------------------------------------------------------------

class TestHealthScoring:
    def test_perfect_score(self):
        health = SystemBiosHealth(
            system="Test", total_bios=2, required_bios=1,
            found=2, valid=2, missing_required=0,
        )
        health.files = [
            BiosFileResult("a.bin", "Test", True, "abc", "abc", True, "/a", True, "valid"),
            BiosFileResult("b.bin", "Test", False, "def", "def", True, "/b", True, "valid"),
        ]
        assert _calc_health_score(health) == 100.0

    def test_zero_score(self):
        health = SystemBiosHealth(
            system="Test", total_bios=1, required_bios=1,
            found=0, valid=0, missing_required=1,
        )
        health.files = [
            BiosFileResult("a.bin", "Test", True, "abc", "", False, "", False, "missing"),
        ]
        score = _calc_health_score(health)
        assert score < 25  # mostly 0 since required is missing

    def test_classify_critical(self):
        health = SystemBiosHealth(system="T", missing_required=1, bad_hash=0, health_score=0)
        assert _classify_health(health) == "critical"

    def test_classify_degraded(self):
        health = SystemBiosHealth(system="T", missing_required=0, bad_hash=1, health_score=70)
        assert _classify_health(health) == "degraded"

    def test_classify_healthy(self):
        health = SystemBiosHealth(system="T", missing_required=0, bad_hash=0, health_score=90)
        assert _classify_health(health) == "healthy"


# ---------------------------------------------------------------------------
# audit_all_bios
# ---------------------------------------------------------------------------

class TestAuditAllBios:
    def test_audit_specific_systems(self, tmp_bios_dir):
        report = audit_all_bios(
            retroarch_system=str(tmp_bios_dir),
            systems=["PlayStation", "Sega Saturn"],
        )
        assert isinstance(report, BiosAuditReport)
        assert report.total_systems == 2
        assert len(report.systems) == 2
        system_names = {s.system for s in report.systems}
        assert "PlayStation" in system_names
        assert "Sega Saturn" in system_names

    def test_audit_all_known(self, tmp_bios_dir):
        report = audit_all_bios(retroarch_system=str(tmp_bios_dir))
        assert report.total_systems == len(KNOWN_BIOS)
        assert report.total_bios_checked > 0

    def test_audit_unknown_system_skipped(self, tmp_bios_dir):
        report = audit_all_bios(
            retroarch_system=str(tmp_bios_dir),
            systems=["NonExistentSystem9999"],
        )
        assert report.total_systems == 0

    def test_report_to_dict(self, tmp_bios_dir):
        report = audit_all_bios(
            retroarch_system=str(tmp_bios_dir),
            systems=["Game Boy Advance"],
        )
        d = report.to_dict()
        assert "systems" in d
        assert "total_systems" in d
        assert isinstance(d["systems"], list)
        assert d["total_systems"] == 1

    def test_report_with_valid_bios(self, tmp_bios_dir):
        """Place a valid GBA BIOS and verify it's detected."""
        gba_entry = KNOWN_BIOS["Game Boy Advance"][0]
        # Create a file with the expected MD5 (fake it by patching)
        content = b"FAKE_GBA_BIOS"
        fake_md5 = hashlib.md5(content).hexdigest()
        (tmp_bios_dir / "gba_bios.bin").write_bytes(content)

        # Temporarily patch the known MD5 to match our fake
        original_md5 = gba_entry.md5
        gba_entry.md5 = fake_md5
        try:
            report = audit_all_bios(
                retroarch_system=str(tmp_bios_dir),
                systems=["Game Boy Advance"],
            )
            gba_health = report.systems[0]
            assert gba_health.found >= 1
            assert gba_health.valid >= 1
            assert gba_health.status == "healthy"
        finally:
            gba_entry.md5 = original_md5


# ---------------------------------------------------------------------------
# load_bios_dat and merge_bios_database
# ---------------------------------------------------------------------------

class TestCustomDat:
    def test_load_valid_dat(self, tmp_path):
        dat_file = tmp_path / "custom_bios.dat"
        dat_file.write_text(
            "# Comment line\n"
            "CustomSystem\tcustom_bios.bin\tabcdef1234567890abcdef1234567890\ttrue\tCustom BIOS\n"
            "CustomSystem\tcustom_opt.bin\t1234567890abcdef1234567890abcdef\tfalse\tOptional\n",
            encoding="utf-8",
        )
        entries = load_bios_dat(dat_file)
        assert "CustomSystem" in entries
        assert len(entries["CustomSystem"]) == 2
        assert entries["CustomSystem"][0].required is True
        assert entries["CustomSystem"][1].required is False

    def test_load_missing_dat(self, tmp_path):
        entries = load_bios_dat(tmp_path / "nonexistent.dat")
        assert entries == {}

    def test_load_malformed_lines(self, tmp_path):
        dat_file = tmp_path / "bad.dat"
        dat_file.write_text("only_one_column\n", encoding="utf-8")
        entries = load_bios_dat(dat_file)
        assert entries == {}

    def test_merge_new_system(self):
        custom = {
            "BrandNewSystem": [
                BiosEntry("new.bin", "aaaa" * 8, True, "New BIOS"),
            ]
        }
        was_present = "BrandNewSystem" in KNOWN_BIOS
        merge_bios_database(custom)
        assert "BrandNewSystem" in KNOWN_BIOS
        assert len(KNOWN_BIOS["BrandNewSystem"]) == 1
        # Cleanup
        if not was_present:
            del KNOWN_BIOS["BrandNewSystem"]

    def test_merge_existing_system_no_dupes(self):
        original_count = len(KNOWN_BIOS.get("PlayStation", []))
        custom = {
            "PlayStation": [
                # This filename already exists — should NOT be added
                BiosEntry("scph5501.bin", "490f666e1afb15b7571ff3f97f93b789", True, "Dupe"),
            ]
        }
        merge_bios_database(custom)
        assert len(KNOWN_BIOS["PlayStation"]) == original_count


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_list_known_systems(self):
        systems = list_known_systems()
        assert isinstance(systems, list)
        assert len(systems) > 0
        assert systems == sorted(systems)  # alphabetically sorted
        assert "PlayStation" in systems
        assert "Neo Geo" in systems

    def test_get_system_requirements(self):
        reqs = get_system_requirements("PlayStation")
        assert isinstance(reqs, list)
        assert len(reqs) > 0
        assert all("filename" in r for r in reqs)
        assert all("md5" in r for r in reqs)

    def test_get_system_requirements_unknown(self):
        reqs = get_system_requirements("UnknownSystem")
        assert reqs == []

    def test_get_missing_bios_summary(self, tmp_bios_dir):
        # Use a custom system so real drives don't interfere
        custom_entries = [
            BiosEntry("totally_fake_bios_xyz.bin", "dead" * 8, True, "Fake required"),
        ]
        health = audit_system_bios("FakeSummarySystem", [tmp_bios_dir], bios_entries=custom_entries)
        report = BiosAuditReport(total_systems=1, systems=[health])
        missing = get_missing_bios_summary(report)
        assert isinstance(missing, list)
        assert len(missing) > 0
        assert all("system" in m for m in missing)
        assert all("filename" in m for m in missing)


# ---------------------------------------------------------------------------
# _build_search_paths
# ---------------------------------------------------------------------------

class TestBuildSearchPaths:
    def test_with_retroarch_system(self, tmp_path):
        ra_sys = tmp_path / "system"
        ra_sys.mkdir()
        paths = _build_search_paths(retroarch_system=str(ra_sys))
        assert Path(str(ra_sys)) in paths

    def test_with_nonexistent_retroarch(self, tmp_path):
        paths = _build_search_paths(retroarch_system=str(tmp_path / "nope"))
        # Should not crash, just return whatever else it finds
        assert isinstance(paths, list)

    def test_with_emulators_root(self, tmp_path):
        emu_root = tmp_path / "emulators"
        emu_root.mkdir()
        (emu_root / "MAME").mkdir()
        (emu_root / "MAME" / "bios").mkdir()
        paths = _build_search_paths(emulators_root=str(emu_root))
        # Should find the MAME/bios subdir
        bios_paths = [str(p) for p in paths]
        assert any("MAME" in p for p in bios_paths)

    def test_with_extra_paths(self, tmp_path):
        extra = tmp_path / "extra_bios"
        extra.mkdir()
        paths = _build_search_paths(extra_paths=[str(extra)])
        assert Path(str(extra)) in paths

    def test_empty_params(self):
        paths = _build_search_paths()
        assert isinstance(paths, list)


# ---------------------------------------------------------------------------
# BiosEntry / BiosFileResult / SystemBiosHealth dataclasses
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_bios_entry_to_dict(self):
        e = BiosEntry("test.bin", "abc123", True, "Test", "System")
        d = e.to_dict()
        assert d["filename"] == "test.bin"
        assert d["system"] == "System"

    def test_bios_file_result_to_dict(self):
        r = BiosFileResult("test.bin", "Sys", True, "abc", "abc", True, "/p", True, "valid", "Desc")
        d = r.to_dict()
        assert d["status"] == "valid"
        assert d["found"] is True

    def test_system_bios_health_to_dict(self):
        h = SystemBiosHealth(system="Test", total_bios=1)
        d = h.to_dict()
        assert d["system"] == "Test"
        assert isinstance(d["files"], list)
        assert isinstance(d["issues"], list)

    def test_bios_audit_report_to_dict(self):
        r = BiosAuditReport(total_systems=1)
        d = r.to_dict()
        assert d["total_systems"] == 1
        assert isinstance(d["systems"], list)
