"""ROM Audit Engine tests — CRC32/SHA1 hashing, DAT parsing, verification."""
from __future__ import annotations

import hashlib
import binascii
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_config
load_config(PROJECT_ROOT / "config.yaml", reload=True)

from engines.rom_audit import (
    hash_file_crc32, hash_file_sha1, hash_rom, hash_zip_contents,
    DATEntry, parse_dat_file, _parse_dat_xml, _parse_dat_clrmamepro,
    verify_roms, VerifyResult, _detect_header_skip,
)


# ═══════════════════════════════════════════════════════════════════════
# Hashing
# ═══════════════════════════════════════════════════════════════════════

class TestCRC32Hashing(unittest.TestCase):

    def test_crc32_known_value(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"hello world")
            fpath = Path(f.name)
        try:
            result = hash_file_crc32(fpath)
            expected = f"{binascii.crc32(b'hello world') & 0xFFFFFFFF:08x}"
            self.assertEqual(result, expected)
        finally:
            fpath.unlink(missing_ok=True)

    def test_crc32_with_header_skip(self):
        header = b"\x00" * 16
        body = b"rom data here"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".nes") as f:
            f.write(header + body)
            fpath = Path(f.name)
        try:
            result = hash_file_crc32(fpath, skip_header=16)
            expected = f"{binascii.crc32(body) & 0xFFFFFFFF:08x}"
            self.assertEqual(result, expected)
        finally:
            fpath.unlink(missing_ok=True)

    def test_crc32_nonexistent(self):
        result = hash_file_crc32(Path("Z:\\no\\file.bin"))
        self.assertEqual(result, "")

    def test_crc32_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            fpath = Path(f.name)
        try:
            result = hash_file_crc32(fpath)
            self.assertEqual(result, "00000000")
        finally:
            fpath.unlink(missing_ok=True)


class TestSHA1Hashing(unittest.TestCase):

    def test_sha1_known_value(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"test data")
            fpath = Path(f.name)
        try:
            result = hash_file_sha1(fpath)
            expected = hashlib.sha1(b"test data").hexdigest()
            self.assertEqual(result, expected)
        finally:
            fpath.unlink(missing_ok=True)

    def test_sha1_nonexistent(self):
        result = hash_file_sha1(Path("Z:\\no\\file.bin"))
        self.assertEqual(result, "")


class TestHashRom(unittest.TestCase):

    def test_hash_rom_crc32(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"rom content")
            fpath = Path(f.name)
        try:
            result = hash_rom(fpath, "crc32")
            self.assertTrue(len(result) == 8)
        finally:
            fpath.unlink(missing_ok=True)

    def test_hash_rom_sha1(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"rom content")
            fpath = Path(f.name)
        try:
            result = hash_rom(fpath, "sha1")
            self.assertTrue(len(result) == 40)
        finally:
            fpath.unlink(missing_ok=True)

    def test_hash_rom_invalid_algorithm(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
            f.write(b"x")
            fpath = Path(f.name)
        try:
            with self.assertRaises(ValueError):
                hash_rom(fpath, "invalid")
        finally:
            fpath.unlink(missing_ok=True)


class TestHeaderDetection(unittest.TestCase):

    def test_nes_header(self):
        self.assertEqual(_detect_header_skip(Path("game.nes")), 16)

    def test_lnx_header(self):
        self.assertEqual(_detect_header_skip(Path("game.lnx")), 64)

    def test_a78_header(self):
        self.assertEqual(_detect_header_skip(Path("game.a78")), 128)

    def test_zip_no_header(self):
        self.assertEqual(_detect_header_skip(Path("game.zip")), 0)

    def test_smc_with_copier_header(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".smc") as f:
            # Size % 1024 == 512 => copier header present
            f.write(b"\x00" * (1024 + 512))
            fpath = Path(f.name)
        try:
            self.assertEqual(_detect_header_skip(fpath), 512)
        finally:
            fpath.unlink(missing_ok=True)

    def test_smc_without_copier_header(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".smc") as f:
            f.write(b"\x00" * 2048)
            fpath = Path(f.name)
        try:
            self.assertEqual(_detect_header_skip(fpath), 0)
        finally:
            fpath.unlink(missing_ok=True)


class TestHashZipContents(unittest.TestCase):

    def test_hash_zip_contents(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            fpath = Path(f.name)
        try:
            with zipfile.ZipFile(fpath, "w") as zf:
                zf.writestr("rom1.bin", b"data1")
                zf.writestr("rom2.bin", b"data2")
            results = hash_zip_contents(fpath)
            self.assertEqual(len(results), 2)
            for r in results:
                self.assertIn("name", r)
                self.assertIn("crc32", r)
                self.assertIn("sha1", r)
                self.assertEqual(len(r["crc32"]), 8)
                self.assertEqual(len(r["sha1"]), 40)
        finally:
            fpath.unlink(missing_ok=True)

    def test_hash_zip_bad_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"not a zip")
            fpath = Path(f.name)
        try:
            results = hash_zip_contents(fpath)
            self.assertEqual(results, [])
        finally:
            fpath.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# DAT Parsing
# ═══════════════════════════════════════════════════════════════════════

class TestDATEntry(unittest.TestCase):

    def test_entry_fields(self):
        e = DATEntry("pacman", "pacman.6e", size=4096, crc32="0xE87E9E6b", sha1="abcd1234")
        self.assertEqual(e.game_name, "pacman")
        self.assertEqual(e.rom_name, "pacman.6e")
        self.assertEqual(e.size, 4096)
        self.assertEqual(e.crc32, "e87e9e6b")  # lowercase, stripped 0x
        self.assertEqual(e.sha1, "abcd1234")

    def test_entry_repr(self):
        e = DATEntry("game", "rom.bin", crc32="12345678")
        self.assertIn("game", repr(e))


class TestParseXMLDAT(unittest.TestCase):

    def test_parse_mame_xml(self):
        xml_content = """<?xml version="1.0"?>
<mame>
  <machine name="pacman">
    <rom name="pacman.6e" size="4096" crc="e87e9e6b" sha1="abcd1234"/>
    <rom name="pacman.6f" size="4096" crc="1a6fb2d4" sha1="ef567890"/>
  </machine>
  <machine name="galaga">
    <rom name="galaga.bin" size="8192" crc="aabbccdd"/>
  </machine>
</mame>"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="w") as f:
            f.write(xml_content)
            fpath = Path(f.name)
        try:
            entries = parse_dat_file(fpath)
            self.assertEqual(len(entries), 3)
            self.assertEqual(entries[0].game_name, "pacman")
            self.assertEqual(entries[0].crc32, "e87e9e6b")
            self.assertEqual(entries[0].sha1, "abcd1234")
            self.assertEqual(entries[2].game_name, "galaga")
        finally:
            fpath.unlink(missing_ok=True)

    def test_parse_logiqx_xml(self):
        xml_content = """<?xml version="1.0"?>
<datafile>
  <game name="sonic">
    <rom name="sonic.bin" size="524288" crc="aa00bbcc" sha1="deadbeef"/>
  </game>
</datafile>"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xml", mode="w") as f:
            f.write(xml_content)
            fpath = Path(f.name)
        try:
            entries = parse_dat_file(fpath)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].game_name, "sonic")
            self.assertEqual(entries[0].crc32, "aa00bbcc")
        finally:
            fpath.unlink(missing_ok=True)


class TestParseCLRMameProDAT(unittest.TestCase):

    def test_parse_clrmamepro(self):
        dat_content = """clrmamepro (
  name "Test Set"
  description "Test"
)

game (
  name "pacman"
  rom ( name "pacman.6e" size 4096 crc e87e9e6b sha1 abcd1234 )
  rom ( name "pacman.6f" size 4096 crc 1a6fb2d4 )
)

game (
  name "galaga"
  rom ( name "galaga.bin" size 8192 crc aabbccdd )
)
"""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat", mode="w") as f:
            f.write(dat_content)
            fpath = Path(f.name)
        try:
            entries = parse_dat_file(fpath)
            self.assertEqual(len(entries), 3)
            names = {e.game_name for e in entries}
            self.assertIn("pacman", names)
            self.assertIn("galaga", names)
        finally:
            fpath.unlink(missing_ok=True)


class TestParseDATEdgeCases(unittest.TestCase):

    def test_nonexistent_dat(self):
        entries = parse_dat_file(Path("Z:\\nonexistent.dat"))
        self.assertEqual(entries, [])

    def test_unknown_format(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".dat", mode="w") as f:
            f.write("random garbage content with no known format markers")
            fpath = Path(f.name)
        try:
            entries = parse_dat_file(fpath)
            self.assertEqual(entries, [])
        finally:
            fpath.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════════════
# Verification Engine
# ═══════════════════════════════════════════════════════════════════════

class TestVerifyRoms(unittest.TestCase):

    def _make_dat_and_roms(self, tmpdir: str) -> tuple[Path, Path]:
        """Create a temp DAT file and matching ROM ZIPs."""
        rom_dir = Path(tmpdir) / "roms"
        rom_dir.mkdir()

        # Create ZIP ROMs with known content
        rom1_content = b"pacman rom data"
        rom1_crc = f"{binascii.crc32(rom1_content) & 0xFFFFFFFF:08x}"
        rom1_sha1 = hashlib.sha1(rom1_content).hexdigest()

        with zipfile.ZipFile(rom_dir / "pacman.zip", "w") as zf:
            zf.writestr("pacman.6e", rom1_content)

        rom2_content = b"galaga rom data"
        rom2_crc = f"{binascii.crc32(rom2_content) & 0xFFFFFFFF:08x}"

        with zipfile.ZipFile(rom_dir / "galaga.zip", "w") as zf:
            zf.writestr("galaga.bin", rom2_content)

        # Create DAT
        dat_path = Path(tmpdir) / "test.xml"
        dat_path.write_text(f"""<?xml version="1.0"?>
<mame>
  <machine name="pacman">
    <rom name="pacman.6e" size="{len(rom1_content)}" crc="{rom1_crc}" sha1="{rom1_sha1}"/>
  </machine>
  <machine name="galaga">
    <rom name="galaga.bin" size="{len(rom2_content)}" crc="{rom2_crc}"/>
  </machine>
  <machine name="missing_game">
    <rom name="missing.bin" size="1024" crc="deadbeef"/>
  </machine>
</mame>""")
        return rom_dir, dat_path

    def test_verify_all_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir, dat_path = self._make_dat_and_roms(tmpdir)
            result = verify_roms(rom_dir, dat_path, system_name="test")
            self.assertEqual(result["system"], "test")
            self.assertEqual(result["verified"], 2)
            self.assertEqual(result["bad_hash"], 0)
            self.assertGreater(result["missing"], 0)  # missing_game

    def test_verify_with_sha1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir, dat_path = self._make_dat_and_roms(tmpdir)
            result = verify_roms(rom_dir, dat_path, use_sha1=True, system_name="test")
            self.assertEqual(result["verified"], 2)

    def test_verify_extra_roms(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir, dat_path = self._make_dat_and_roms(tmpdir)
            # Add an extra ROM not in DAT
            with zipfile.ZipFile(rom_dir / "extra_game.zip", "w") as zf:
                zf.writestr("extra.bin", b"extra data not in dat")
            result = verify_roms(rom_dir, dat_path, system_name="test")
            self.assertGreater(result["extra"], 0)

    def test_verify_bad_hash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            # ROM with wrong content
            with zipfile.ZipFile(rom_dir / "pacman.zip", "w") as zf:
                zf.writestr("pacman.6e", b"WRONG DATA")

            dat_path = Path(tmpdir) / "test.xml"
            dat_path.write_text("""<?xml version="1.0"?>
<mame>
  <machine name="pacman">
    <rom name="pacman.6e" size="4096" crc="e87e9e6b" sha1="abcd1234"/>
  </machine>
</mame>""")
            result = verify_roms(rom_dir, dat_path, system_name="test")
            self.assertGreater(result["bad_hash"], 0)

    def test_verify_empty_dat(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir = Path(tmpdir) / "roms"
            rom_dir.mkdir()
            dat_path = Path(tmpdir) / "empty.dat"
            dat_path.write_text("random content")
            result = verify_roms(rom_dir, dat_path)
            self.assertIn("error", result)

    def test_verify_nonexistent_rom_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dat_path = Path(tmpdir) / "test.xml"
            dat_path.write_text("""<?xml version="1.0"?>
<mame>
  <machine name="game1">
    <rom name="rom.bin" size="1024" crc="12345678"/>
  </machine>
</mame>""")
            result = verify_roms(Path(tmpdir) / "nonexistent", dat_path)
            self.assertEqual(result["missing"], 1)

    def test_verify_completeness_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rom_dir, dat_path = self._make_dat_and_roms(tmpdir)
            result = verify_roms(rom_dir, dat_path, system_name="test")
            # 2 out of 3 games verified
            self.assertAlmostEqual(result["completeness_pct"], 66.7, places=0)

    def test_verify_result_to_dict(self):
        r = VerifyResult(
            game_name="pac", rom_name="rom.bin",
            status="verified", expected_crc="aabb",
        )
        d = r.to_dict()
        self.assertEqual(d["game_name"], "pac")
        self.assertEqual(d["status"], "verified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
