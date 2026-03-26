"""
tests/test_task503_library.py — Task 5.03 acceptance tests

Verifies GET /jukebox/library:
  - Returns only files within the music root.
  - Metadata fields (path, title, artist, album, duration) are present.
  - Files outside the music root are not accessible.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT  = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "ansible" / "roles" / "jukebox" / "files" / "server"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _fresh_main(tmpdir: str, dbpath: str):
    os.environ["HEARTH_MUSIC_ROOT"] = tmpdir
    os.environ["HEARTH_JUKEBOX_DB"] = dbpath
    for mod in list(sys.modules.keys()):
        if mod in ("main",):
            del sys.modules[mod]
    import main
    return main


class TestTask503Library(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._dbfile.close()

        music_root = Path(cls._tmpdir.name)

        # Create two fake audio files in a subdirectory
        subdir = music_root / "Artist" / "Album"
        subdir.mkdir(parents=True)
        (subdir / "01 - Track One.mp3").write_bytes(b"\xff\xfb" * 64)
        (subdir / "02 - Track Two.mp3").write_bytes(b"\xff\xfb" * 64)
        # A non-audio file (should not appear in library)
        (music_root / "cover.jpg").write_bytes(b"\xff\xd8\xff")

        cls.m = _fresh_main(cls._tmpdir.name, cls._dbfile.name)

        # Reload the library (it was loaded at import time with the tmp dir)
        cls.m.LIBRARY = cls.m.load_library()

        from fastapi.testclient import TestClient
        cls.client = TestClient(cls.m.app)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        Path(cls._dbfile.name).unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Acceptance criterion: library returns audio files within music root
    # ------------------------------------------------------------------

    def test_library_returns_200(self):
        resp = self.client.get("/jukebox/library")
        self.assertEqual(resp.status_code, 200)

    def test_library_returns_list(self):
        resp = self.client.get("/jukebox/library")
        self.assertIsInstance(resp.json(), list)

    def test_library_contains_audio_files(self):
        resp = self.client.get("/jukebox/library")
        paths = [t["path"] for t in resp.json()]
        self.assertTrue(
            any("Track One" in p or "01" in p for p in paths),
            f"Expected Track One in library paths, got: {paths}",
        )

    def test_library_excludes_non_audio_files(self):
        resp = self.client.get("/jukebox/library")
        paths = [t["path"] for t in resp.json()]
        self.assertFalse(
            any(".jpg" in p for p in paths),
            "cover.jpg must not appear in the library",
        )

    # ------------------------------------------------------------------
    # Acceptance criterion: metadata fields present for each track
    # ------------------------------------------------------------------

    def test_each_track_has_required_fields(self):
        resp = self.client.get("/jukebox/library")
        tracks = resp.json()
        self.assertGreater(len(tracks), 0, "Library is empty; expected at least one track")
        for track in tracks:
            for field in ("path", "title", "artist", "album", "duration"):
                self.assertIn(field, track, f"Field '{field}' missing from track: {track}")

    def test_path_is_relative_to_music_root(self):
        resp = self.client.get("/jukebox/library")
        music_root = str(self.m.MUSIC_ROOT)
        for track in resp.json():
            self.assertFalse(
                track["path"].startswith("/"),
                f"path must be relative, got: {track['path']}",
            )
            self.assertNotIn(
                music_root, track["path"],
                f"path must not contain the absolute music root: {track['path']}",
            )

    # ------------------------------------------------------------------
    # Acceptance criterion: files outside music root are not accessible
    # ------------------------------------------------------------------

    def test_load_library_does_not_include_symlink_outside_root(self):
        """Symlinks pointing outside MUSIC_ROOT must be excluded from the library."""
        import os
        music_root = Path(self.m.MUSIC_ROOT)
        # Create a file outside the music root
        outside_dir = tempfile.TemporaryDirectory()
        outside_file = Path(outside_dir.name) / "outside.mp3"
        outside_file.write_bytes(b"\xff\xfb" * 8)
        # Symlink into music root
        symlink = music_root / "link_outside.mp3"
        try:
            symlink.symlink_to(outside_file)
            library = self.m.load_library()
            paths = [t["path"] for t in library]
            self.assertFalse(
                any("link_outside" in p for p in paths),
                "Symlink outside music root must not appear in the library",
            )
        finally:
            symlink.unlink(missing_ok=True)
            outside_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
