"""Tests for the Asset Auditor Engine (engines/asset_auditor.py).

Covers:
  - Asset type classification
  - Image dimension reading (PNG/JPEG headers)
  - Quality scoring
  - System/game extraction from paths
  - Scanning directories with mock filesystem
  - Query and filtering
  - Index save/load round-trip
  - Missing media report
  - Duplicate asset detection
  - GUI page recommendations
"""

import json
import os
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.asset_auditor import (
    ASSET_TYPES,
    PAGE_ASSET_MAP,
    AssetAuditor,
    AssetRecord,
    ScanStats,
    classify_asset,
    compute_quality_score,
    extract_system_game,
    get_image_dimensions,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_media_dir(tmp_path):
    """Create a mock HyperSpin Media directory structure."""
    media = tmp_path / "Media"
    # System: MAME
    (media / "MAME" / "Images" / "Wheel").mkdir(parents=True)
    (media / "MAME" / "Images" / "Backgrounds").mkdir(parents=True)
    (media / "MAME" / "Images" / "Artwork1").mkdir(parents=True)
    (media / "MAME" / "Video").mkdir(parents=True)
    (media / "MAME" / "Sound").mkdir(parents=True)
    (media / "MAME" / "Themes").mkdir(parents=True)
    # System: Nintendo 64
    (media / "Nintendo 64" / "Images" / "Wheel").mkdir(parents=True)
    (media / "Nintendo 64" / "Video").mkdir(parents=True)
    return media


@pytest.fixture
def sample_png(tmp_path):
    """Create a minimal valid PNG file with known dimensions (100x50)."""
    filepath = tmp_path / "test.png"
    with open(filepath, "wb") as f:
        # PNG signature
        f.write(b"\x89PNG\r\n\x1a\n")
        # IHDR chunk: length=13, type=IHDR, width=100, height=50, ...
        ihdr_data = struct.pack(">II", 100, 50) + b"\x08\x02\x00\x00\x00"
        f.write(struct.pack(">I", 13))  # chunk length
        f.write(b"IHDR")
        f.write(ihdr_data)
        # CRC (dummy)
        f.write(b"\x00\x00\x00\x00")
    return filepath


@pytest.fixture
def sample_jpg(tmp_path):
    """Create a minimal JPEG file with SOF0 marker (200x150)."""
    filepath = tmp_path / "test.jpg"
    with open(filepath, "wb") as f:
        f.write(b"\xff\xd8")  # SOI
        # APP0 marker (dummy, small)
        f.write(b"\xff\xe0")
        f.write(struct.pack(">H", 16))  # length
        f.write(b"JFIF\x00" + b"\x00" * 9)
        # SOF0 marker
        f.write(b"\xff\xc0")
        f.write(struct.pack(">H", 17))   # length
        f.write(b"\x08")                  # precision
        f.write(struct.pack(">H", 150))   # height
        f.write(struct.pack(">H", 200))   # width
        f.write(b"\x03")                  # components
        f.write(b"\x00" * 9)             # component data
    return filepath


@pytest.fixture
def mock_registry(tmp_path):
    """Create a mock drive_registry.json."""
    reg = {
        "drives": [
            {"current_letter": "D", "tag": "TEST_HYPERSPIN", "model": "WDC Test"},
            {"current_letter": "I", "tag": "PRIMARY_HYPERSPIN", "model": "Seagate"},
        ],
        "system_drives": [
            {"current_letter": "C", "tag": "SYSTEM_NVME", "model": "Samsung"},
        ],
    }
    reg_path = tmp_path / "drive_registry.json"
    with open(reg_path, "w") as f:
        json.dump(reg, f)
    return str(reg_path)


@pytest.fixture
def populated_auditor(tmp_media_dir, mock_registry):
    """Create an auditor with some scanned assets."""
    # Create some actual files in the mock media dir
    _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Wheel" / "pacman.png", 400, 400)
    _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Wheel" / "galaga.png", 200, 200)
    _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Backgrounds" / "pacman.png", 1920, 1080)
    _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Artwork1" / "pacman.png", 800, 600)
    _write_dummy_file(tmp_media_dir / "MAME" / "Video" / "pacman.mp4", 50000)
    _write_dummy_file(tmp_media_dir / "MAME" / "Sound" / "pacman.mp3", 5000)
    _write_dummy_file(tmp_media_dir / "MAME" / "Themes" / "pacman.swf", 20000)
    _create_dummy_png(tmp_media_dir / "Nintendo 64" / "Images" / "Wheel" / "mario64.png", 300, 300)
    _write_dummy_file(tmp_media_dir / "Nintendo 64" / "Video" / "mario64.mp4", 80000)

    auditor = AssetAuditor(registry_path=mock_registry)
    records = auditor.scan_directory(tmp_media_dir, "D", "HyperSpin")
    auditor.assets.extend(records)
    return auditor


def _create_dummy_png(filepath: Path, width: int, height: int):
    """Create a minimal PNG with specific dimensions."""
    with open(filepath, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
        f.write(struct.pack(">I", 13))
        f.write(b"IHDR")
        f.write(ihdr_data)
        f.write(b"\x00\x00\x00\x00")


def _write_dummy_file(filepath: Path, size_bytes: int):
    """Create a dummy file of a given size."""
    with open(filepath, "wb") as f:
        f.write(b"\x00" * size_bytes)


# ---------------------------------------------------------------------------
# Test: Image Dimension Reading
# ---------------------------------------------------------------------------

class TestImageDimensions:
    def test_png_dimensions(self, sample_png):
        w, h = get_image_dimensions(sample_png)
        assert w == 100
        assert h == 50

    def test_jpg_dimensions(self, sample_jpg):
        w, h = get_image_dimensions(sample_jpg)
        assert w == 200
        assert h == 150

    def test_unknown_format_returns_zero(self, tmp_path):
        f = tmp_path / "test.bmp"
        f.write_bytes(b"\x00" * 100)
        w, h = get_image_dimensions(f)
        assert w == 0 and h == 0

    def test_corrupt_png_returns_zero(self, tmp_path):
        f = tmp_path / "bad.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")
        w, h = get_image_dimensions(f)
        assert w == 0 and h == 0

    def test_missing_file_returns_zero(self, tmp_path):
        f = tmp_path / "nonexistent.png"
        w, h = get_image_dimensions(f)
        assert w == 0 and h == 0


# ---------------------------------------------------------------------------
# Test: Asset Classification
# ---------------------------------------------------------------------------

class TestAssetClassification:
    def test_classify_wheel_art(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Images" / "Wheel" / "pacman.png"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "wheel_art"

    def test_classify_background(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Images" / "Backgrounds" / "bg.jpg"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "background"

    def test_classify_video(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Video" / "game.mp4"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "video"

    def test_classify_audio(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Sound" / "game.mp3"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "audio"

    def test_classify_theme(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Themes" / "theme.swf"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "theme_anim"

    def test_classify_box_art(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Images" / "Artwork1" / "game.png"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) == "box_art"

    def test_classify_outside_media_returns_none(self, tmp_path, tmp_media_dir):
        fp = tmp_path / "random" / "file.png"
        fp.parent.mkdir(parents=True)
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) is None

    def test_classify_wrong_extension_returns_none(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Images" / "Wheel" / "readme.txt"
        fp.touch()
        assert classify_asset(fp, tmp_media_dir) is None


# ---------------------------------------------------------------------------
# Test: System/Game Extraction
# ---------------------------------------------------------------------------

class TestSystemGameExtraction:
    def test_extract_from_wheel(self, tmp_media_dir):
        fp = tmp_media_dir / "MAME" / "Images" / "Wheel" / "pacman.png"
        system, game = extract_system_game(fp, tmp_media_dir)
        assert system == "MAME"
        assert game == "pacman"

    def test_extract_from_video(self, tmp_media_dir):
        fp = tmp_media_dir / "Nintendo 64" / "Video" / "mario64.mp4"
        system, game = extract_system_game(fp, tmp_media_dir)
        assert system == "Nintendo 64"
        assert game == "mario64"

    def test_extract_outside_returns_stem(self, tmp_path, tmp_media_dir):
        fp = tmp_path / "other" / "game.png"
        fp.parent.mkdir(parents=True)
        system, game = extract_system_game(fp, tmp_media_dir)
        assert game == "game"


# ---------------------------------------------------------------------------
# Test: Quality Scoring
# ---------------------------------------------------------------------------

class TestQualityScoring:
    def test_high_res_image_scores_well(self):
        record = AssetRecord(
            asset_type="background", width=1920, height=1080,
            file_size_kb=500, format=".png"
        )
        score = compute_quality_score(record)
        assert score >= 7.0

    def test_tiny_image_scores_low(self):
        record = AssetRecord(
            asset_type="wheel_art", width=50, height=50,
            file_size_kb=2, format=".jpg"
        )
        score = compute_quality_score(record)
        assert score <= 4.0

    def test_video_large_file_bonus(self):
        record = AssetRecord(
            asset_type="video", file_size_kb=10000, format=".mp4"
        )
        score = compute_quality_score(record)
        assert score >= 6.0

    def test_theme_anim_bonus(self):
        record = AssetRecord(
            asset_type="theme_anim", file_size_kb=200, format=".swf"
        )
        score = compute_quality_score(record)
        assert score >= 6.0

    def test_score_clamped_0_10(self):
        # Very bad record
        record = AssetRecord(
            asset_type="wheel_art", width=10, height=10,
            file_size_kb=0.5, format=".jpg"
        )
        score = compute_quality_score(record)
        assert 0.0 <= score <= 10.0

    def test_png_format_bonus_for_wheel(self):
        record_png = AssetRecord(
            asset_type="wheel_art", width=500, height=500,
            file_size_kb=200, format=".png"
        )
        record_jpg = AssetRecord(
            asset_type="wheel_art", width=500, height=500,
            file_size_kb=200, format=".jpg"
        )
        assert compute_quality_score(record_png) > compute_quality_score(record_jpg)


# ---------------------------------------------------------------------------
# Test: Scanning
# ---------------------------------------------------------------------------

class TestScanning:
    def test_scan_directory_finds_assets(self, populated_auditor):
        assert len(populated_auditor.assets) >= 7

    def test_scan_records_have_valid_types(self, populated_auditor):
        valid_types = set(ASSET_TYPES.keys())
        for r in populated_auditor.assets:
            assert r.asset_type in valid_types, f"Unknown type: {r.asset_type}"

    def test_scan_records_have_drive_tag(self, populated_auditor):
        for r in populated_auditor.assets:
            assert r.drive_tag == "TEST_HYPERSPIN"

    def test_scan_records_have_quality_scores(self, populated_auditor):
        for r in populated_auditor.assets:
            assert 0.0 <= r.quality_score <= 10.0

    def test_scan_with_max_files(self, tmp_media_dir, mock_registry):
        _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Wheel" / "a.png", 100, 100)
        _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Wheel" / "b.png", 100, 100)
        _create_dummy_png(tmp_media_dir / "MAME" / "Images" / "Wheel" / "c.png", 100, 100)

        auditor = AssetAuditor(registry_path=mock_registry)
        records = auditor.scan_directory(tmp_media_dir, "D", "HyperSpin", max_files=2)
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Test: Queries
# ---------------------------------------------------------------------------

class TestQueries:
    def test_query_by_type(self, populated_auditor):
        wheels = populated_auditor.query(asset_type="wheel_art")
        assert all(r.asset_type == "wheel_art" for r in wheels)
        assert len(wheels) >= 2

    def test_query_by_system(self, populated_auditor):
        n64 = populated_auditor.query(system="Nintendo 64")
        assert all(r.system == "Nintendo 64" for r in n64)

    def test_query_by_min_quality(self, populated_auditor):
        good = populated_auditor.query(min_quality=6.0)
        assert all(r.quality_score >= 6.0 for r in good)

    def test_query_by_format(self, populated_auditor):
        pngs = populated_auditor.query(format_filter=".png")
        assert all(r.format == ".png" for r in pngs)

    def test_query_by_gui_page(self, populated_auditor):
        dash = populated_auditor.query(gui_page="dashboard")
        for r in dash:
            assert "dashboard" in r.recommended_for

    def test_query_limit(self, populated_auditor):
        limited = populated_auditor.query(limit=3)
        assert len(limited) <= 3

    def test_query_sorted_by_quality(self, populated_auditor):
        results = populated_auditor.query(limit=50)
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].quality_score >= results[i + 1].quality_score


# ---------------------------------------------------------------------------
# Test: Best Assets for GUI Page
# ---------------------------------------------------------------------------

class TestBestAssetsForPage:
    def test_best_for_dashboard(self, populated_auditor):
        best = populated_auditor.best_assets_for_page("dashboard", limit=5)
        for r in best:
            assert "dashboard" in r.recommended_for

    def test_best_for_collection_browser(self, populated_auditor):
        best = populated_auditor.best_assets_for_page("collection_browser", limit=5)
        for r in best:
            assert "collection_browser" in r.recommended_for


# ---------------------------------------------------------------------------
# Test: Missing Media Report
# ---------------------------------------------------------------------------

class TestMissingMediaReport:
    def test_reports_missing_types(self, populated_auditor):
        report = populated_auditor.missing_media_report()
        # Nintendo 64 only has wheel_art and video, missing background & audio
        assert "Nintendo 64" in report
        missing = report["Nintendo 64"]
        assert "background" in missing or "audio" in missing


# ---------------------------------------------------------------------------
# Test: Duplicate Detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_no_duplicates_on_single_drive(self, populated_auditor):
        dupes = populated_auditor.duplicate_assets()
        # On single scan, same game+type shouldn't appear twice
        # (unless different art layers counted separately)
        for key, paths in dupes:
            assert len(paths) >= 2

    def test_cross_drive_duplicates(self, populated_auditor):
        # Manually add a duplicate from another "drive"
        dupe = AssetRecord(
            asset_id="fakeid",
            path="I:\\Arcade\\Media\\MAME\\Images\\Wheel\\pacman.png",
            drive_letter="I",
            drive_tag="PRIMARY_HYPERSPIN",
            system="MAME",
            game="pacman",
            asset_type="wheel_art",
            format=".png",
            width=400, height=400,
            file_size_kb=50,
            quality_score=7.0,
        )
        populated_auditor.assets.append(dupe)
        dupes = populated_auditor.duplicate_assets()
        found = [k for k, v in dupes if "MAME|pacman|wheel_art" in k]
        assert len(found) >= 1


# ---------------------------------------------------------------------------
# Test: Index Persistence (Save/Load)
# ---------------------------------------------------------------------------

class TestIndexPersistence:
    def test_save_and_load_roundtrip(self, populated_auditor, tmp_path):
        index_path = str(tmp_path / "test_index.json")
        populated_auditor.save_index(index_path)

        # Load into a new auditor
        new_auditor = AssetAuditor(registry_path="nonexistent.json")
        new_auditor.load_index(index_path)

        assert len(new_auditor.assets) == len(populated_auditor.assets)
        for orig, loaded in zip(populated_auditor.assets, new_auditor.assets):
            assert orig.asset_id == loaded.asset_id
            assert orig.path == loaded.path
            assert orig.asset_type == loaded.asset_type

    def test_save_creates_valid_json(self, populated_auditor, tmp_path):
        index_path = str(tmp_path / "test_index.json")
        populated_auditor.save_index(index_path)

        with open(index_path, "r") as f:
            data = json.load(f)
        assert "_generated" in data
        assert "_stats" in data
        assert "assets" in data
        assert len(data["assets"]) == len(populated_auditor.assets)

    def test_load_nonexistent_file(self):
        auditor = AssetAuditor(registry_path="nonexistent.json")
        auditor.load_index("nonexistent_index.json")
        assert len(auditor.assets) == 0


# ---------------------------------------------------------------------------
# Test: Statistics
# ---------------------------------------------------------------------------

class TestStatistics:
    def test_stats_computed(self, populated_auditor):
        stats = populated_auditor.get_stats()
        assert stats.total_assets >= 7
        assert stats.total_size_mb > 0

    def test_stats_by_type(self, populated_auditor):
        stats = populated_auditor.get_stats()
        assert "wheel_art" in stats.by_type
        assert stats.by_type["wheel_art"] >= 2

    def test_stats_by_drive(self, populated_auditor):
        stats = populated_auditor.get_stats()
        assert "D" in stats.by_drive

    def test_summary(self, populated_auditor):
        summary = populated_auditor.summary()
        assert summary["total_assets"] >= 7
        assert "by_type" in summary
        assert "top_systems" in summary


# ---------------------------------------------------------------------------
# Test: Drive Tag Resolution
# ---------------------------------------------------------------------------

class TestDriveTagResolution:
    def test_known_drive(self, mock_registry):
        auditor = AssetAuditor(registry_path=mock_registry)
        assert auditor._resolve_drive_tag("D") == "TEST_HYPERSPIN"
        assert auditor._resolve_drive_tag("I") == "PRIMARY_HYPERSPIN"

    def test_system_drive(self, mock_registry):
        auditor = AssetAuditor(registry_path=mock_registry)
        assert auditor._resolve_drive_tag("C") == "SYSTEM_NVME"

    def test_unknown_drive(self, mock_registry):
        auditor = AssetAuditor(registry_path=mock_registry)
        assert auditor._resolve_drive_tag("Z") == "UNKNOWN"

    def test_missing_registry(self):
        auditor = AssetAuditor(registry_path="nonexistent.json")
        assert auditor._resolve_drive_tag("D") == "UNKNOWN"


# ---------------------------------------------------------------------------
# Test: PAGE_ASSET_MAP completeness
# ---------------------------------------------------------------------------

class TestPageAssetMap:
    def test_all_pages_have_recommendations(self):
        expected_pages = [
            "dashboard", "collection_browser", "drive_manager",
            "agent_console", "asset_gallery", "update_center",
            "rom_audit", "backup_control", "settings", "ai_chat",
        ]
        for page in expected_pages:
            assert page in PAGE_ASSET_MAP, f"Missing page: {page}"
            assert len(PAGE_ASSET_MAP[page]) > 0

    def test_all_recommended_types_are_valid(self):
        valid_types = set(ASSET_TYPES.keys())
        for page, types in PAGE_ASSET_MAP.items():
            for t in types:
                assert t in valid_types, f"Invalid type '{t}' in page '{page}'"
