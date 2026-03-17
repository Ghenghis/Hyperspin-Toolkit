"""M10 — HyperSpin XML Tools tests: validate, merge, rebuild, filter, sort, stats."""
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

from engines.xml_tools import (
    validate_xml, merge_xml, rebuild_xml, filter_xml, sort_xml, stats_xml,
)

SAMPLE_XML = """\
<?xml version='1.0' encoding='us-ascii'?>
<menu>
  <header>
    <listname>TestSystem</listname>
    <lastlistupdate>2025-01-01</lastlistupdate>
    <listversion>1.0</listversion>
    <exporterversion>Test</exporterversion>
  </header>
  <game name="pacman">
    <description>Pac-Man</description>
    <year>1980</year>
    <manufacturer>Namco</manufacturer>
    <genre>Maze</genre>
    <rating></rating>
    <enabled>Yes</enabled>
  </game>
  <game name="galaga">
    <description>Galaga</description>
    <year>1981</year>
    <manufacturer>Namco</manufacturer>
    <genre>Shooter</genre>
    <rating></rating>
    <enabled>Yes</enabled>
  </game>
  <game name="dkong">
    <description>Donkey Kong</description>
    <year>1981</year>
    <manufacturer>Nintendo</manufacturer>
    <genre>Platform</genre>
    <rating></rating>
    <enabled>Yes</enabled>
  </game>
</menu>"""

SAMPLE_XML_2 = """\
<?xml version='1.0' encoding='us-ascii'?>
<menu>
  <game name="galaga">
    <description>Galaga (updated)</description>
    <year>1981</year>
    <manufacturer>Namco</manufacturer>
    <genre>Shoot-em-up</genre>
    <rating>5</rating>
    <enabled>Yes</enabled>
  </game>
  <game name="digdug">
    <description>Dig Dug</description>
    <year>1982</year>
    <manufacturer>Namco</manufacturer>
    <genre>Maze</genre>
    <rating></rating>
    <enabled>Yes</enabled>
  </game>
</menu>"""


def _write_temp_xml(content: str, tmpdir: str, name: str = "test.xml") -> Path:
    p = Path(tmpdir) / name
    p.write_text(content, encoding="utf-8")
    return p


# ═══════════════════════════════════════════════════════════════════════
# Validate
# ═══════════════════════════════════════════════════════════════════════

class TestValidateXML(unittest.TestCase):

    def test_valid_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(SAMPLE_XML, tmpdir)
            result = validate_xml(xp)
            self.assertTrue(result["valid"])
            self.assertEqual(result["game_count"], 3)
            self.assertEqual(len(result["duplicates"]), 0)

    def test_nonexistent(self):
        result = validate_xml(Path("Z:\\no\\file.xml"))
        self.assertFalse(result["valid"])
        self.assertTrue(any(i["type"] == "not_found" for i in result["issues"]))

    def test_malformed_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml("<broken><unclosed>", tmpdir)
            result = validate_xml(xp)
            self.assertFalse(result["valid"])
            self.assertTrue(any(i["type"] == "parse_error" for i in result["issues"]))

    def test_duplicate_names(self):
        dupe_xml = SAMPLE_XML.replace(
            '</menu>',
            '  <game name="pacman"><description>Pac-Man Clone</description></game>\n</menu>'
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(dupe_xml, tmpdir)
            result = validate_xml(xp)
            self.assertEqual(len(result["duplicates"]), 1)
            self.assertEqual(result["duplicates"][0]["name"], "pacman")

    def test_empty_xml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml('<?xml version="1.0"?><menu></menu>', tmpdir)
            result = validate_xml(xp)
            self.assertTrue(result["valid"])
            self.assertEqual(result["game_count"], 0)
            self.assertTrue(any(i["type"] == "empty" for i in result["issues"]))

    def test_wrong_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml('<?xml version="1.0"?><games><game name="x"/></games>', tmpdir)
            result = validate_xml(xp)
            self.assertTrue(any(i["type"] == "wrong_root" for i in result["issues"]))


# ═══════════════════════════════════════════════════════════════════════
# Merge
# ═══════════════════════════════════════════════════════════════════════

class TestMergeXML(unittest.TestCase):

    def test_merge_basic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = _write_temp_xml(SAMPLE_XML, tmpdir, "a.xml")
            f2 = _write_temp_xml(SAMPLE_XML_2, tmpdir, "b.xml")
            out = Path(tmpdir) / "merged.xml"
            result = merge_xml([f1, f2], out)
            self.assertEqual(result["total_input"], 5)
            self.assertEqual(result["merged_count"], 4)  # pacman, galaga, dkong, digdug
            self.assertGreater(result["duplicates_removed"], 0)
            self.assertTrue(out.exists())

    def test_merge_prefer_last(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = _write_temp_xml(SAMPLE_XML, tmpdir, "a.xml")
            f2 = _write_temp_xml(SAMPLE_XML_2, tmpdir, "b.xml")
            out = Path(tmpdir) / "merged.xml"
            merge_xml([f1, f2], out, prefer_last=True)
            # Re-parse and check galaga has updated description
            from engines.xml_tools import _parse_games, _game_to_dict
            _, games = _parse_games(out)
            galaga = [_game_to_dict(g) for g in games if g.get("name") == "galaga"]
            self.assertEqual(len(galaga), 1)
            self.assertIn("updated", galaga[0]["description"])

    def test_merge_no_dedup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = _write_temp_xml(SAMPLE_XML, tmpdir, "a.xml")
            f2 = _write_temp_xml(SAMPLE_XML_2, tmpdir, "b.xml")
            out = Path(tmpdir) / "merged.xml"
            result = merge_xml([f1, f2], out, dedup=False)
            self.assertEqual(result["merged_count"], 5)

    def test_merge_single_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = _write_temp_xml(SAMPLE_XML, tmpdir, "a.xml")
            out = Path(tmpdir) / "merged.xml"
            result = merge_xml([f1], out)
            self.assertEqual(result["merged_count"], 3)


# ═══════════════════════════════════════════════════════════════════════
# Rebuild
# ═══════════════════════════════════════════════════════════════════════

class TestRebuildXML(unittest.TestCase):

    def test_rebuild_from_roms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            (rom_dir / "pacman.zip").write_bytes(b"fake")
            (rom_dir / "galaga.zip").write_bytes(b"fake")
            (rom_dir / "readme.txt").write_text("ignore")  # not a ROM ext

            out = Path(tmpdir) / "rebuilt.xml"
            result = rebuild_xml(rom_dir, out, system_name="MAME")
            self.assertEqual(result["rom_count"], 2)
            self.assertEqual(result["without_metadata"], 2)
            self.assertTrue(out.exists())

    def test_rebuild_with_reference(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            (rom_dir / "pacman.zip").write_bytes(b"fake")
            (rom_dir / "galaga.zip").write_bytes(b"fake")
            (rom_dir / "newgame.zip").write_bytes(b"fake")

            ref = _write_temp_xml(SAMPLE_XML, tmpdir, "ref.xml")
            out = Path(tmpdir) / "rebuilt.xml"
            result = rebuild_xml(rom_dir, out, reference_xml=ref)
            self.assertEqual(result["rom_count"], 3)
            self.assertEqual(result["with_metadata"], 2)
            self.assertEqual(result["without_metadata"], 1)

    def test_rebuild_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            out = Path(tmpdir) / "rebuilt.xml"
            result = rebuild_xml(rom_dir, out)
            self.assertEqual(result["rom_count"], 0)


# ═══════════════════════════════════════════════════════════════════════
# Filter
# ═══════════════════════════════════════════════════════════════════════

class TestFilterXML(unittest.TestCase):

    def test_filter_to_roms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(SAMPLE_XML, tmpdir)
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            (rom_dir / "pacman.zip").write_bytes(b"fake")
            # galaga and dkong should be removed

            out = Path(tmpdir) / "filtered.xml"
            result = filter_xml(xp, rom_dir, out)
            self.assertEqual(result["original_count"], 3)
            self.assertEqual(result["filtered_count"], 1)
            self.assertEqual(result["removed_count"], 2)

    def test_filter_all_present(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(SAMPLE_XML, tmpdir)
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            for name in ("pacman", "galaga", "dkong"):
                (rom_dir / f"{name}.zip").write_bytes(b"fake")

            out = Path(tmpdir) / "filtered.xml"
            result = filter_xml(xp, rom_dir, out)
            self.assertEqual(result["filtered_count"], 3)
            self.assertEqual(result["removed_count"], 0)


# ═══════════════════════════════════════════════════════════════════════
# Sort
# ═══════════════════════════════════════════════════════════════════════

class TestSortXML(unittest.TestCase):

    def test_sort_alphabetical(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(SAMPLE_XML, tmpdir)
            out = Path(tmpdir) / "sorted.xml"
            result = sort_xml(xp, out)
            self.assertEqual(result["game_count"], 3)

            from engines.xml_tools import _parse_games
            _, games = _parse_games(out)
            names = [g.get("name") for g in games]
            self.assertEqual(names, ["dkong", "galaga", "pacman"])


# ═══════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════

class TestStatsXML(unittest.TestCase):

    def test_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            xp = _write_temp_xml(SAMPLE_XML, tmpdir)
            result = stats_xml(xp)
            self.assertEqual(result["game_count"], 3)
            self.assertTrue(result["has_header"])
            self.assertEqual(result["year_range"]["min"], "1980")
            self.assertEqual(result["year_range"]["max"], "1981")
            self.assertTrue(len(result["top_manufacturers"]) > 0)
            self.assertTrue(len(result["top_genres"]) > 0)

    def test_stats_nonexistent(self):
        result = stats_xml(Path("Z:\\no\\file.xml"))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
