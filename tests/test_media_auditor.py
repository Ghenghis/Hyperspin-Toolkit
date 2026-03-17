"""Media Asset Auditor tests — corruption detection, coverage, orphan detection."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_config
load_config(PROJECT_ROOT / "config.yaml", reload=True)

from engines.media_auditor import (
    is_corrupt_image, is_corrupt_video, is_corrupt_file,
    _get_game_names_from_xml, audit_media_for_system,
    MEDIA_TYPES,
)


# ═══════════════════════════════════════════════════════════════════════
# Corruption detection
# ═══════════════════════════════════════════════════════════════════════

class TestCorruptionDetection(unittest.TestCase):

    def test_valid_png(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_image(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_corrupt_png(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            f.write(b"NOT_A_PNG" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertTrue(is_corrupt_image(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_valid_jpg(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_image(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_corrupt_jpg(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(b"\x00\x00\x00\x00")
            fpath = Path(f.name)
        try:
            self.assertTrue(is_corrupt_image(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_valid_gif(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as f:
            f.write(b"GIF89a" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_image(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_valid_flv(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".flv") as f:
            f.write(b"FLV" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_video(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_corrupt_flv(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".flv") as f:
            f.write(b"XXXX")
            fpath = Path(f.name)
        try:
            self.assertTrue(is_corrupt_video(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_valid_mp4(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as f:
            f.write(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100)
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_video(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_zero_byte_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
            fpath = Path(f.name)
        try:
            self.assertTrue(is_corrupt_file(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_unknown_extension_not_flagged(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xyz") as f:
            f.write(b"some data")
            fpath = Path(f.name)
        try:
            self.assertFalse(is_corrupt_image(fpath))
            self.assertFalse(is_corrupt_video(fpath))
        finally:
            fpath.unlink(missing_ok=True)

    def test_nonexistent_file(self):
        self.assertTrue(is_corrupt_file(Path("Z:\\no\\file.png")))


# ═══════════════════════════════════════════════════════════════════════
# XML game extraction
# ═══════════════════════════════════════════════════════════════════════

class TestGameNameExtraction(unittest.TestCase):

    def test_extract_names(self):
        xml = """<?xml version="1.0"?>
<menu>
  <game name="pacman"><description>Pac-Man</description></game>
  <game name="galaga"><description>Galaga</description></game>
</menu>"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="w") as f:
            f.write(xml)
            fpath = Path(f.name)
        try:
            names = _get_game_names_from_xml(fpath)
            self.assertEqual(names, ["pacman", "galaga"])
        finally:
            fpath.unlink(missing_ok=True)

    def test_nonexistent_xml(self):
        names = _get_game_names_from_xml(Path("Z:\\no.xml"))
        self.assertEqual(names, [])

    def test_empty_xml(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="w") as f:
            f.write("<menu></menu>")
            fpath = Path(f.name)
        try:
            names = _get_game_names_from_xml(fpath)
            self.assertEqual(names, [])
        finally:
            fpath.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# Media audit with fixture
# ═══════════════════════════════════════════════════════════════════════

class TestAuditMediaForSystem(unittest.TestCase):

    def _build_fixture(self, tmpdir: str) -> str:
        """Build a minimal HyperSpin-like media tree. Returns system_name."""
        system = "TestSystem"
        base = Path(tmpdir)

        # XML database
        db_dir = base / "Databases" / system
        db_dir.mkdir(parents=True)
        (db_dir / f"{system}.xml").write_text("""<?xml version="1.0"?>
<menu>
  <game name="game_a"><description>Game A</description></game>
  <game name="game_b"><description>Game B</description></game>
  <game name="game_c"><description>Game C</description></game>
</menu>""")

        # Media — wheel (2 of 3 present, 1 corrupt)
        wheel_dir = base / "Media" / system / "Images" / "Wheel"
        wheel_dir.mkdir(parents=True)
        (wheel_dir / "game_a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
        (wheel_dir / "game_b.png").write_bytes(b"CORRUPT DATA NOT PNG")
        # game_c missing
        # orphan file
        (wheel_dir / "orphan_game.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        # Media — video (1 of 3 present)
        vid_dir = base / "Media" / system / "Video"
        vid_dir.mkdir(parents=True)
        (vid_dir / "game_a.mp4").write_bytes(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100)

        return system

    def test_audit_coverage(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmpdir:
            system = self._build_fixture(tmpdir)
            base = Path(tmpdir)
            with patch("engines.media_auditor.cfg_get") as mock_cfg:
                def _cfg(key, default=""):
                    return {
                        "paths.hyperspin_root": str(base),
                        "paths.media_root": str(base / "Media"),
                        "paths.databases_root": str(base / "Databases"),
                    }.get(key, default)
                mock_cfg.side_effect = _cfg

                result = audit_media_for_system(system)

        self.assertEqual(result["system"], "TestSystem")
        self.assertEqual(result["game_count"], 3)

        # Wheel: 2 files (game_a valid, game_b corrupt, orphan not counted as match)
        wheel = result["media_types"]["wheel"]
        self.assertEqual(wheel["missing_count"], 1)  # game_c
        self.assertEqual(wheel["corrupt_count"], 1)   # game_b
        self.assertEqual(wheel["orphaned_count"], 1)  # orphan_game

        # Video: 1 of 3
        video = result["media_types"]["video"]
        self.assertEqual(video["missing_count"], 2)
        self.assertAlmostEqual(video["coverage_pct"], 33.3, places=0)

    def test_audit_summary_totals(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmpdir:
            system = self._build_fixture(tmpdir)
            base = Path(tmpdir)
            with patch("engines.media_auditor.cfg_get") as mock_cfg:
                def _cfg(key, default=""):
                    return {
                        "paths.hyperspin_root": str(base),
                        "paths.media_root": str(base / "Media"),
                        "paths.databases_root": str(base / "Databases"),
                    }.get(key, default)
                mock_cfg.side_effect = _cfg

                result = audit_media_for_system(system)

        self.assertGreater(result["summary"]["total_missing"], 0)
        self.assertGreater(result["summary"]["total_corrupt"], 0)
        self.assertGreater(result["summary"]["total_orphaned"], 0)

    def test_audit_no_xml(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("engines.media_auditor.cfg_get") as mock_cfg:
                def _cfg(key, default=""):
                    return {
                        "paths.hyperspin_root": str(tmpdir),
                        "paths.media_root": str(Path(tmpdir) / "Media"),
                        "paths.databases_root": str(Path(tmpdir) / "Databases"),
                    }.get(key, default)
                mock_cfg.side_effect = _cfg

                result = audit_media_for_system("NoSystem")

        self.assertEqual(result["game_count"], 0)
        self.assertTrue(any(i["type"] == "no_games" for i in result["issues"]))


# ═══════════════════════════════════════════════════════════════════════
# Media type definitions
# ═══════════════════════════════════════════════════════════════════════

class TestMediaTypeDefinitions(unittest.TestCase):

    def test_all_types_have_paths(self):
        for name, mdef in MEDIA_TYPES.items():
            self.assertIn("paths", mdef, f"{name} missing paths")
            self.assertGreater(len(mdef["paths"]), 0)

    def test_all_types_have_extensions(self):
        for name, mdef in MEDIA_TYPES.items():
            self.assertIn("extensions", mdef)
            self.assertGreater(len(mdef["extensions"]), 0)

    def test_required_types(self):
        required = [n for n, m in MEDIA_TYPES.items() if m["required"]]
        self.assertIn("wheel", required)
        self.assertIn("video", required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
