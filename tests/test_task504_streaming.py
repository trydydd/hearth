"""
tests/test_task504_streaming.py — Task 5.04 acceptance tests

Verifies GET /jukebox/stream:
  - Returns 204 when the jukebox is IDLE.
  - Returns 206 Partial Content on a valid Range request while PLAYING.
  - Returns Accept-Ranges: bytes header.
  - Serves audio content (not an error page).
"""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

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


class TestTask504Streaming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._dbfile.close()

        cls.music_root = Path(cls._tmpdir.name)
        # Create a realistic fake audio file (256 bytes)
        cls.track_file = cls.music_root / "test_track.mp3"
        cls.track_file.write_bytes(b"\xff\xfb\x90\x00" * 64)  # 256 bytes

        cls.m = _fresh_main(cls._tmpdir.name, cls._dbfile.name)

        from fastapi.testclient import TestClient
        cls.client = TestClient(cls.m.app)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        Path(cls._dbfile.name).unlink(missing_ok=True)

    def _set_playing(self, path_rel: str, duration: int = 60):
        """Helper: force playback state to PLAYING with given track."""
        loop = asyncio.new_event_loop()
        track = {
            "path": path_rel, "title": "Test", "artist": "", "album": "",
            "duration": duration, "nick": "",
        }
        loop.run_until_complete(self.m.playback.start_track(track))
        loop.close()

    def _set_idle(self):
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self.m.playback.stop())
        loop.close()

    # ------------------------------------------------------------------
    # Acceptance criterion: 204 when IDLE
    # ------------------------------------------------------------------

    def test_stream_returns_204_when_idle(self):
        self._set_idle()
        resp = self.client.get("/jukebox/stream")
        self.assertEqual(resp.status_code, 204)

    # ------------------------------------------------------------------
    # Acceptance criterion: 200 with Accept-Ranges when playing
    # ------------------------------------------------------------------

    def test_stream_returns_200_while_playing(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get("/jukebox/stream")
        self.assertIn(resp.status_code, (200, 206))
        self.assertEqual(resp.headers.get("accept-ranges", "").lower(), "bytes")

    def test_stream_has_accept_ranges_header(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get("/jukebox/stream")
        self.assertIn("bytes", resp.headers.get("accept-ranges", ""))

    # ------------------------------------------------------------------
    # Acceptance criterion: 206 on Range request while playing
    # ------------------------------------------------------------------

    def test_stream_returns_206_on_range_request(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get(
            "/jukebox/stream",
            headers={"Range": "bytes=0-63"},
        )
        self.assertEqual(resp.status_code, 206)

    def test_stream_range_response_has_content_range_header(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get(
            "/jukebox/stream",
            headers={"Range": "bytes=0-63"},
        )
        self.assertIn("content-range", resp.headers)
        self.assertTrue(resp.headers["content-range"].startswith("bytes 0-"))

    def test_stream_range_response_body_length(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get(
            "/jukebox/stream",
            headers={"Range": "bytes=0-63"},
        )
        self.assertEqual(resp.status_code, 206)
        self.assertEqual(len(resp.content), 64)

    # ------------------------------------------------------------------
    # Acceptance criterion: response is audio content (not HTML error)
    # ------------------------------------------------------------------

    def test_stream_content_type_is_audio(self):
        rel = str(self.track_file.relative_to(self.music_root))
        self._set_playing(rel)
        resp = self.client.get("/jukebox/stream")
        ct = resp.headers.get("content-type", "")
        self.assertTrue(
            ct.startswith("audio/"),
            f"Expected audio/* content-type, got: {ct}",
        )


if __name__ == "__main__":
    unittest.main()
