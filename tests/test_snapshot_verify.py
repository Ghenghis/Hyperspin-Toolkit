"""Tests for M14 — Pre/Post Update Snapshot Verification."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engines.snapshot_verify import (
    FileEntry,
    Snapshot,
    DiffResult,
    _hash_file,
    capture_snapshot,
    load_snapshot,
    compare_snapshots,
    verify_update,
    list_snapshots,
    snapshot_summary,
    ensure_tables,
)


class TestFileEntry(unittest.TestCase):
    def test_to_dict(self):
        fe = FileEntry(path="/tmp/a.txt", relative_path="a.txt",
                       size_bytes=100, modified=1000.0, sha256="abc123")
        d = fe.to_dict()
        self.assertEqual(d["path"], "/tmp/a.txt")
        self.assertEqual(d["size_bytes"], 100)
        self.assertEqual(d["sha256"], "abc123")

    def test_defaults(self):
        fe = FileEntry(path="/x", relative_path="x", size_bytes=0, modified=0.0)
        self.assertEqual(fe.sha256, "")


class TestSnapshot(unittest.TestCase):
    def test_properties(self):
        files = [
            FileEntry("/a", "a", 100, 1.0),
            FileEntry("/b", "b", 200, 2.0),
        ]
        snap = Snapshot(name="test", target_path="/tmp", snapshot_type="pre", files=files)
        self.assertEqual(snap.file_count, 2)
        self.assertEqual(snap.total_size, 300)

    def test_to_dict(self):
        snap = Snapshot(name="s1", target_path="/tmp", snapshot_type="manual")
        d = snap.to_dict()
        self.assertEqual(d["name"], "s1")
        self.assertEqual(d["file_count"], 0)


class TestDiffResult(unittest.TestCase):
    def test_no_changes(self):
        diff = DiffResult(pre_snapshot="a", post_snapshot="b", unchanged=5)
        self.assertFalse(diff.has_changes)
        self.assertEqual(diff.change_count, 0)

    def test_has_changes(self):
        diff = DiffResult(pre_snapshot="a", post_snapshot="b",
                          added=[{"relative_path": "new.txt"}])
        self.assertTrue(diff.has_changes)
        self.assertEqual(diff.change_count, 1)

    def test_to_dict(self):
        diff = DiffResult(pre_snapshot="a", post_snapshot="b",
                          added=[{"x": 1}], removed=[{"y": 2}], unchanged=3)
        d = diff.to_dict()
        self.assertEqual(d["summary"]["added"], 1)
        self.assertEqual(d["summary"]["removed"], 1)
        self.assertEqual(d["summary"]["unchanged"], 3)


class TestHashFile(unittest.TestCase):
    def test_hash_file(self):
        fd, fpath = tempfile.mkstemp(suffix=".txt")
        try:
            os.write(fd, b"hello world")
            os.close(fd)
            h = _hash_file(Path(fpath))
            self.assertIsInstance(h, str)
            self.assertEqual(len(h), 64)  # SHA256 hex length
        finally:
            try:
                os.unlink(fpath)
            except OSError:
                pass

    def test_nonexistent(self):
        h = _hash_file(Path("/nonexistent/file.txt"))
        self.assertEqual(h, "")


class TestCaptureSnapshot(unittest.TestCase):
    @patch("engines.snapshot_verify.db")
    @patch("engines.snapshot_verify.cfg_get", return_value="")
    def test_capture_basic(self, _cfg, mock_db):
        mock_db.insert.return_value = 1
        mock_db.get_conn.return_value.__enter__ = MagicMock()
        mock_db.get_conn.return_value.__exit__ = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            # Use tmp as output root for manifests
            _cfg.return_value = tmp

            # Create test files
            (Path(tmp) / "file1.txt").write_text("hello")
            (Path(tmp) / "file2.bin").write_bytes(b"\x00" * 100)
            subdir = Path(tmp) / "sub"
            subdir.mkdir()
            (subdir / "file3.txt").write_text("world")

            snap = capture_snapshot(tmp, name="test_snap", snapshot_type="pre")
            # At least the snapshot manifest itself + our 3 files
            self.assertGreaterEqual(snap.file_count, 3)
            self.assertEqual(snap.name, "test_snap")
            self.assertEqual(snap.snapshot_type, "pre")

    def test_nonexistent_target(self):
        with self.assertRaises(FileNotFoundError):
            capture_snapshot("/nonexistent/path/12345")


class TestCompareSnapshots(unittest.TestCase):
    @patch("engines.snapshot_verify.db")
    @patch("engines.snapshot_verify.cfg_get", return_value="")
    def test_compare_detects_changes(self, _cfg, mock_db):
        mock_db.insert.return_value = 1
        mock_db.get_conn.return_value.__enter__ = MagicMock()
        mock_db.get_conn.return_value.__exit__ = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            _cfg.return_value = tmp

            # Create initial files
            (Path(tmp) / "keep.txt").write_text("keep")
            (Path(tmp) / "modify.txt").write_text("before")
            (Path(tmp) / "remove.txt").write_text("gone")

            snap_pre = capture_snapshot(tmp, name="cmp_pre", snapshot_type="pre")

            # Make changes
            (Path(tmp) / "modify.txt").write_text("after_modified_content")
            (Path(tmp) / "remove.txt").unlink()
            (Path(tmp) / "added.txt").write_text("new")

            snap_post = capture_snapshot(tmp, name="cmp_post", snapshot_type="post")

            # Mock DB to return the manifest paths for load_snapshot
            snap_dir = Path(tmp) / "snapshots"
            def fake_execute(sql, params=()):
                if "SELECT * FROM snapshots WHERE name" in sql:
                    name = params[0]
                    mp = str(snap_dir / f"{name}.json")
                    if (snap_dir / f"{name}.json").exists():
                        return [{"id": 1, "manifest_path": mp}]
                return []
            mock_db.execute.side_effect = fake_execute

            diff = compare_snapshots("cmp_pre", "cmp_post")
            self.assertTrue(diff.has_changes)
            added_names = [f["relative_path"] for f in diff.added]
            removed_names = [f["relative_path"] for f in diff.removed]
            self.assertIn("added.txt", added_names)
            self.assertIn("remove.txt", removed_names)


class TestListSnapshots(unittest.TestCase):
    @patch("engines.snapshot_verify.db")
    def test_returns_list(self, mock_db):
        mock_db.execute.return_value = []
        result = list_snapshots()
        self.assertIsInstance(result, list)


class TestSnapshotSummary(unittest.TestCase):
    @patch("engines.snapshot_verify.db")
    def test_summary_structure(self, mock_db):
        mock_db.execute.side_effect = [
            [{"cnt": 5}],      # total
            [],                 # by_type
            [],                 # by_status
            [],                 # recent
        ]
        result = snapshot_summary()
        self.assertIn("total_snapshots", result)
        self.assertIn("by_type", result)
        self.assertIn("by_status", result)


if __name__ == "__main__":
    unittest.main()
