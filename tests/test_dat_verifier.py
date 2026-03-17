"""Tests for the DAT File ROM Set Verification Engine (engines/dat_verifier.py).

Covers:
  - DAT source identification (No-Intro, Redump, TOSEC, MAME)
  - DAT metadata parsing (XML and CLRMamePro headers)
  - Region detection from game names
  - Non-game entry filtering (BIOS, demos, protos)
  - Base name extraction
  - 1G1R curation with region priority
  - System verification with completion tracking
  - Multi-system batch verification
  - DAT index management
  - Dataclass serialization
"""

import hashlib
import tempfile
from pathlib import Path

import pytest

from engines.dat_verifier import (
    DEFAULT_REGION_PRIORITY,
    DATMetadata,
    DATVerificationReport,
    OneG1REntry,
    SystemCompletion,
    curate_1g1r,
    detect_regions,
    extract_base_name,
    get_dat_summary,
    identify_dat_source,
    index_dat_directory,
    is_nongame,
    parse_dat_metadata,
    verify_system,
    _find_rom_dir,
    _infer_system_from_filename,
)
from engines.rom_audit import DATEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dat_dir(tmp_path):
    """Create a temp directory for DAT files."""
    dat_dir = tmp_path / "DATs"
    dat_dir.mkdir()
    return dat_dir


@pytest.fixture
def tmp_rom_dir(tmp_path):
    """Create a temp directory with sample ROM files."""
    rom_dir = tmp_path / "ROMs" / "TestSystem"
    rom_dir.mkdir(parents=True)
    return rom_dir


@pytest.fixture
def sample_logiqx_dat(tmp_dat_dir):
    """Create a sample Logiqx XML DAT file (No-Intro style)."""
    content = """<?xml version="1.0"?>
<!DOCTYPE datafile SYSTEM "http://www.logiqx.com/Dats/datafile.dtd">
<datafile>
    <header>
        <name>No-Intro - TestSystem</name>
        <description>No-Intro - TestSystem (20230101-123456)</description>
        <version>20230101-123456</version>
        <author>No-Intro</author>
        <homepage>https://no-intro.org</homepage>
    </header>
    <game name="Game Alpha (USA)">
        <rom name="Game Alpha (USA).zip" size="1024" crc="aabbccdd" sha1="1234567890abcdef1234567890abcdef12345678"/>
    </game>
    <game name="Game Alpha (Europe)">
        <rom name="Game Alpha (Europe).zip" size="1024" crc="11223344" sha1="abcdef1234567890abcdef1234567890abcdef12"/>
    </game>
    <game name="Game Alpha (Japan)">
        <rom name="Game Alpha (Japan).zip" size="1024" crc="55667788" sha1="fedcba0987654321fedcba0987654321fedcba09"/>
    </game>
    <game name="Game Beta (USA)">
        <rom name="Game Beta (USA).zip" size="2048" crc="deadbeef" sha1="aabbccdd11223344556677889900aabbccddeeff"/>
    </game>
    <game name="Game Gamma (World)">
        <rom name="Game Gamma (World).zip" size="512" crc="cafebabe"/>
    </game>
    <game name="[BIOS] System BIOS (USA)">
        <rom name="[BIOS] System BIOS (USA).zip" size="256" crc="b105b105"/>
    </game>
    <game name="Game Delta (Proto) (USA)">
        <rom name="Game Delta (Proto) (USA).zip" size="512" crc="deadd00d"/>
    </game>
</datafile>"""
    dat_file = tmp_dat_dir / "No-Intro - TestSystem.xml"
    dat_file.write_text(content, encoding="utf-8")
    return dat_file


@pytest.fixture
def sample_clrmamepro_dat(tmp_dat_dir):
    """Create a sample CLRMamePro format DAT file."""
    content = """clrmamepro (
    name "Redump - Sega Dreamcast"
    description "Redump - Sega Dreamcast (20230615)"
    version "20230615"
    author "Redump"
    homepage "http://redump.org"
)

game (
    name "Sonic Adventure (USA)"
    rom ( name "Sonic Adventure (USA).bin" size 1073741824 crc aabb1122 md5 1234567890abcdef1234567890abcdef sha1 aabbccdd11223344556677889900aabbccddeeff )
)

game (
    name "Sonic Adventure (Europe)"
    rom ( name "Sonic Adventure (Europe).bin" size 1073741824 crc ccdd3344 md5 abcdef1234567890abcdef1234567890 sha1 11223344556677889900aabbccddeeff00112233 )
)

game (
    name "Crazy Taxi (USA)"
    rom ( name "Crazy Taxi (USA).bin" size 536870912 crc eeff5566 )
)
"""
    dat_file = tmp_dat_dir / "Redump - Sega Dreamcast.dat"
    dat_file.write_text(content, encoding="utf-8")
    return dat_file


# ---------------------------------------------------------------------------
# identify_dat_source
# ---------------------------------------------------------------------------

class TestIdentifyDatSource:
    def test_nointro_by_filename(self, tmp_path):
        f = tmp_path / "No-Intro - Nintendo - NES.xml"
        assert identify_dat_source(f) == "No-Intro"

    def test_redump_by_filename(self, tmp_path):
        f = tmp_path / "Redump - Sony - PlayStation.dat"
        assert identify_dat_source(f) == "Redump"

    def test_tosec_by_filename(self, tmp_path):
        f = tmp_path / "TOSEC - Atari 2600.dat"
        assert identify_dat_source(f) == "TOSEC"

    def test_mame_by_content(self, tmp_path):
        f = tmp_path / "arcade.dat"
        assert identify_dat_source(f, content='<?xml version="1.0"?><mame build="0.260">') == "MAME"

    def test_unknown_source(self, tmp_path):
        f = tmp_path / "random_file.dat"
        assert identify_dat_source(f) == "Unknown"


# ---------------------------------------------------------------------------
# parse_dat_metadata
# ---------------------------------------------------------------------------

class TestParseDatMetadata:
    def test_xml_metadata(self, sample_logiqx_dat):
        meta = parse_dat_metadata(sample_logiqx_dat)
        assert meta.name == "No-Intro - TestSystem"
        assert meta.version == "20230101-123456"
        assert meta.author == "No-Intro"
        assert meta.source == "No-Intro"
        assert meta.total_games == 7
        assert meta.total_roms == 7

    def test_clrmamepro_metadata(self, sample_clrmamepro_dat):
        meta = parse_dat_metadata(sample_clrmamepro_dat)
        assert meta.name == "Redump - Sega Dreamcast"
        assert meta.source == "Redump"
        assert meta.total_games == 3

    def test_missing_dat(self, tmp_path):
        meta = parse_dat_metadata(tmp_path / "nonexistent.dat")
        assert meta.name == ""
        assert meta.total_games == 0

    def test_metadata_to_dict(self, sample_logiqx_dat):
        meta = parse_dat_metadata(sample_logiqx_dat)
        d = meta.to_dict()
        assert "name" in d
        assert "source" in d
        assert "total_games" in d


# ---------------------------------------------------------------------------
# _infer_system_from_filename
# ---------------------------------------------------------------------------

class TestInferSystem:
    def test_nointro_prefix(self):
        p = Path("No-Intro - Nintendo - Game Boy Advance.xml")
        assert _infer_system_from_filename(p) == "Nintendo - Game Boy Advance"

    def test_redump_prefix(self):
        p = Path("Redump - Sony - PlayStation 2.dat")
        assert _infer_system_from_filename(p) == "Sony - PlayStation 2"

    def test_tosec_prefix(self):
        p = Path("TOSEC - Atari 2600.dat")
        assert _infer_system_from_filename(p) == "Atari 2600"

    def test_no_prefix(self):
        p = Path("MAME 0.260.dat")
        assert _infer_system_from_filename(p) == "MAME 0.260"

    def test_version_suffix_stripped(self):
        p = Path("No-Intro - NES (20231201-123456).xml")
        assert _infer_system_from_filename(p) == "NES"


# ---------------------------------------------------------------------------
# detect_regions
# ---------------------------------------------------------------------------

class TestDetectRegions:
    def test_single_region_usa(self):
        assert detect_regions("Super Mario Bros. (USA)") == ["USA"]

    def test_single_region_japan(self):
        assert detect_regions("Super Mario Bros. (Japan)") == ["Japan"]

    def test_multi_region(self):
        regions = detect_regions("Sonic (USA, Europe)")
        assert "USA" in regions
        assert "Europe" in regions

    def test_world_region(self):
        assert detect_regions("Tetris (World)") == ["World"]

    def test_no_region(self):
        assert detect_regions("Some Random Game") == []

    def test_case_insensitive(self):
        # Our patterns are case-insensitive
        regions = detect_regions("Game (usa)")
        assert "USA" in regions


# ---------------------------------------------------------------------------
# is_nongame
# ---------------------------------------------------------------------------

class TestIsNongame:
    def test_bios(self):
        assert is_nongame("[BIOS] PlayStation (USA)") is True

    def test_proto(self):
        assert is_nongame("Game Name (Proto) (USA)") is True

    def test_beta(self):
        assert is_nongame("Game Name (Beta) (USA)") is True

    def test_demo(self):
        assert is_nongame("Game Name (Demo) (USA)") is True

    def test_normal_game(self):
        assert is_nongame("Super Mario Bros. (USA)") is False

    def test_sample(self):
        assert is_nongame("Sample Program (USA) (Sample)") is True


# ---------------------------------------------------------------------------
# extract_base_name
# ---------------------------------------------------------------------------

class TestExtractBaseName:
    def test_strip_region(self):
        assert extract_base_name("Super Mario Bros. (USA)") == "Super Mario Bros."

    def test_strip_multiple_tags(self):
        assert extract_base_name("Game (USA) (Rev 1)") == "Game"

    def test_strip_brackets(self):
        assert extract_base_name("Game [!] (USA)") == "Game"

    def test_no_tags(self):
        assert extract_base_name("Plain Game Name") == "Plain Game Name"

    def test_complex_name(self):
        result = extract_base_name("Sonic the Hedgehog (Japan, Europe) (Rev A)")
        assert result == "Sonic the Hedgehog"


# ---------------------------------------------------------------------------
# curate_1g1r
# ---------------------------------------------------------------------------

class TestCurate1G1R:
    def test_basic_curation(self):
        entries = [
            DATEntry("Game Alpha (USA)", "Game Alpha (USA).zip", crc32="aabb"),
            DATEntry("Game Alpha (Europe)", "Game Alpha (Europe).zip", crc32="ccdd"),
            DATEntry("Game Alpha (Japan)", "Game Alpha (Japan).zip", crc32="eeff"),
        ]
        result = curate_1g1r(entries)
        assert len(result) == 1
        assert result[0].base_name == "Game Alpha"
        assert result[0].selected_game == "Game Alpha (USA)"
        assert result[0].region == "USA"

    def test_japan_priority(self):
        entries = [
            DATEntry("Game (Europe)", "a.zip", crc32="aa"),
            DATEntry("Game (Japan)", "b.zip", crc32="bb"),
        ]
        result = curate_1g1r(entries, region_priority=["Japan", "Europe", "USA"])
        assert len(result) == 1
        assert result[0].selected_game == "Game (Japan)"
        assert result[0].region == "Japan"

    def test_nongame_excluded(self):
        entries = [
            DATEntry("Game (USA)", "a.zip", crc32="aa"),
            DATEntry("[BIOS] System (USA)", "b.zip", crc32="bb"),
            DATEntry("Demo Game (Demo) (USA)", "c.zip", crc32="cc"),
        ]
        result = curate_1g1r(entries, exclude_nongame=True)
        assert len(result) == 1
        assert result[0].base_name == "Game"

    def test_nongame_included(self):
        entries = [
            DATEntry("Game (USA)", "a.zip", crc32="aa"),
            DATEntry("[BIOS] System (USA)", "b.zip", crc32="bb"),
        ]
        result = curate_1g1r(entries, exclude_nongame=False)
        assert len(result) == 2

    def test_multiple_games(self):
        entries = [
            DATEntry("Alpha (USA)", "a.zip"),
            DATEntry("Alpha (Europe)", "b.zip"),
            DATEntry("Beta (USA)", "c.zip"),
            DATEntry("Beta (Japan)", "d.zip"),
            DATEntry("Gamma (World)", "e.zip"),
        ]
        result = curate_1g1r(entries)
        assert len(result) == 3
        names = {r.base_name for r in result}
        assert names == {"Alpha", "Beta", "Gamma"}

    def test_empty_entries(self):
        result = curate_1g1r([])
        assert result == []

    def test_all_variants_tracked(self):
        entries = [
            DATEntry("Game (USA)", "a.zip"),
            DATEntry("Game (Europe)", "b.zip"),
            DATEntry("Game (Japan)", "c.zip"),
        ]
        result = curate_1g1r(entries)
        assert len(result[0].all_variants) == 3

    def test_1g1r_to_dict(self):
        entry = OneG1REntry("Game", "Game (USA)", "USA", "aabb", ["Game (USA)", "Game (EU)"])
        d = entry.to_dict()
        assert d["base_name"] == "Game"
        assert d["region"] == "USA"
        assert len(d["all_variants"]) == 2


# ---------------------------------------------------------------------------
# verify_system
# ---------------------------------------------------------------------------

class TestVerifySystem:
    def test_verify_with_matching_roms(self, tmp_rom_dir, sample_logiqx_dat):
        """Verify returns completion data even if ROMs don't match hashes."""
        # Create dummy ROM files
        (tmp_rom_dir / "Game Alpha (USA).zip").write_bytes(b"fake_rom_data")
        (tmp_rom_dir / "Game Beta (USA).zip").write_bytes(b"fake_rom_data_2")

        comp = verify_system(
            "TestSystem", tmp_rom_dir, sample_logiqx_dat,
            compute_1g1r=True,
        )
        assert isinstance(comp, SystemCompletion)
        assert comp.system == "TestSystem"
        assert comp.dat_source == "No-Intro"
        assert comp.total_on_disk >= 2
        assert comp.oneg1r_total > 0  # 1G1R was computed

    def test_verify_empty_rom_dir(self, tmp_path, sample_logiqx_dat):
        empty_dir = tmp_path / "empty_roms"
        empty_dir.mkdir()
        comp = verify_system("TestSystem", empty_dir, sample_logiqx_dat)
        assert comp.total_on_disk == 0
        assert comp.missing > 0

    def test_verify_to_dict(self, tmp_rom_dir, sample_logiqx_dat):
        comp = verify_system("TestSystem", tmp_rom_dir, sample_logiqx_dat)
        d = comp.to_dict()
        assert "system" in d
        assert "completeness_pct" in d
        assert "oneg1r_pct" in d

    def test_verify_no_1g1r(self, tmp_rom_dir, sample_logiqx_dat):
        comp = verify_system(
            "TestSystem", tmp_rom_dir, sample_logiqx_dat,
            compute_1g1r=False,
        )
        assert comp.oneg1r_total == 0


# ---------------------------------------------------------------------------
# _find_rom_dir
# ---------------------------------------------------------------------------

class TestFindRomDir:
    def test_direct_match(self, tmp_path):
        roms_root = tmp_path / "ROMs"
        target = roms_root / "NES"
        target.mkdir(parents=True)
        assert _find_rom_dir("NES", roms_root, tmp_path) == target

    def test_roms_subdir(self, tmp_path):
        roms_root = tmp_path / "ROMs"
        target = roms_root / "NES" / "roms"
        target.mkdir(parents=True)
        # _find_rom_dir returns first match; parent NES/ dir also exists
        result = _find_rom_dir("NES", roms_root, tmp_path)
        assert result is not None
        assert "NES" in str(result)

    def test_not_found(self, tmp_path):
        roms_root = tmp_path / "ROMs"
        roms_root.mkdir()
        assert _find_rom_dir("NonExistent", roms_root, tmp_path) is None


# ---------------------------------------------------------------------------
# index_dat_directory
# ---------------------------------------------------------------------------

class TestIndexDatDirectory:
    def test_index_with_files(self, tmp_dat_dir, sample_logiqx_dat, sample_clrmamepro_dat):
        index = index_dat_directory(tmp_dat_dir)
        assert len(index) == 2
        sources = {m.source for m in index}
        assert "No-Intro" in sources
        assert "Redump" in sources

    def test_index_empty_dir(self, tmp_path):
        empty = tmp_path / "empty_dats"
        empty.mkdir()
        index = index_dat_directory(empty)
        assert index == []

    def test_index_nonexistent(self, tmp_path):
        index = index_dat_directory(tmp_path / "nope")
        assert index == []

    def test_get_dat_summary(self, tmp_dat_dir, sample_logiqx_dat, sample_clrmamepro_dat):
        summary = get_dat_summary(tmp_dat_dir)
        assert summary["total_dat_files"] == 2
        assert summary["total_games"] > 0
        assert "by_source" in summary
        assert "No-Intro" in summary["by_source"]


# ---------------------------------------------------------------------------
# DATVerificationReport
# ---------------------------------------------------------------------------

class TestDATVerificationReport:
    def test_to_dict(self):
        report = DATVerificationReport(systems_checked=2)
        d = report.to_dict()
        assert d["systems_checked"] == 2
        assert isinstance(d["systems"], list)

    def test_with_systems(self):
        comp = SystemCompletion(system="NES", completeness_pct=85.0)
        report = DATVerificationReport(
            systems_checked=1,
            total_verified=100,
            systems=[comp],
        )
        d = report.to_dict()
        assert len(d["systems"]) == 1
        assert d["systems"][0]["system"] == "NES"
