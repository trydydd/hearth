"""
tests/test_task502_playback_engine.py — Task 5.02 acceptance tests

Verifies the playback state machine:
  - Enqueueing a track while IDLE transitions to PLAYING.
  - Queue advances when a track finishes.
  - PlaybackState tracks elapsed time correctly.
"""

import asyncio
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "ansible" / "roles" / "jukebox" / "files" / "server"

if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))


def _fresh_main(tmpdir: str, dbpath: str):
    """Import a fresh copy of main.py with given paths, avoiding module cache."""
    os.environ["HEARTH_MUSIC_ROOT"] = tmpdir
    os.environ["HEARTH_JUKEBOX_DB"] = dbpath
    for mod in list(sys.modules.keys()):
        if mod in ("main",):
            del sys.modules[mod]
    import main
    return main


class TestTask502PlaybackState(unittest.TestCase):
    """Unit tests for the PlaybackState class in isolation."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._dbfile.close()
        self.m = _fresh_main(self._tmpdir.name, self._dbfile.name)

    def tearDown(self):
        self._tmpdir.cleanup()
        Path(self._dbfile.name).unlink(missing_ok=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_initial_state_is_idle(self):
        ps = self.m.PlaybackState()
        self.assertFalse(ps.is_playing)
        self.assertIsNone(ps.now_playing)

    def test_start_track_transitions_to_playing(self):
        ps = self.m.PlaybackState()
        track = {"path": "test.mp3", "title": "Test", "duration": 10, "nick": ""}
        self._run(ps.start_track(track))
        self.assertTrue(ps.is_playing)
        self.assertEqual(ps.now_playing["title"], "Test")
        self.assertEqual(ps.elapsed, 0.0)

    def test_tick_increments_elapsed(self):
        ps = self.m.PlaybackState()
        track = {"path": "test.mp3", "title": "Test", "duration": 10, "nick": ""}
        self._run(ps.start_track(track))
        still, elapsed, dur = self._run(ps.tick())
        self.assertTrue(still)
        self.assertEqual(elapsed, 1.0)

    def test_tick_while_idle_returns_false(self):
        ps = self.m.PlaybackState()
        still, elapsed, dur = self._run(ps.tick())
        self.assertFalse(still)
        self.assertEqual(elapsed, 0.0)

    def test_stop_transitions_to_idle(self):
        ps = self.m.PlaybackState()
        track = {"path": "test.mp3", "title": "Test", "duration": 10, "nick": ""}
        self._run(ps.start_track(track))
        self._run(ps.stop())
        self.assertFalse(ps.is_playing)
        self.assertIsNone(ps.now_playing)

    def test_snapshot_idle(self):
        ps = self.m.PlaybackState()
        snap = ps.snapshot()
        self.assertIsNone(snap["now_playing"])
        self.assertEqual(snap["elapsed"], 0)

    def test_snapshot_playing(self):
        ps = self.m.PlaybackState()
        track = {"path": "test.mp3", "title": "Test", "duration": 60, "nick": "bob"}
        self._run(ps.start_track(track))
        self._run(ps.tick())
        snap = ps.snapshot()
        self.assertIsNotNone(snap["now_playing"])
        self.assertEqual(snap["elapsed"], 1)
        self.assertEqual(snap["duration"], 60)


class TestTask502QueueAdvance(unittest.TestCase):
    """Integration: enqueuing while IDLE starts playback; track end advances queue."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._dbfile.close()

        # Create a minimal fake audio file so path validation passes
        self._track_path = Path(self._tmpdir.name) / "track01.mp3"
        self._track_path.write_bytes(b"\xff\xfb\x90\x00" * 16)

        self.m = _fresh_main(self._tmpdir.name, self._dbfile.name)
        self.m.init_db()

    def tearDown(self):
        self._tmpdir.cleanup()
        Path(self._dbfile.name).unlink(missing_ok=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_enqueue_while_idle_starts_playback(self):
        """
        Simulate one engine iteration: queue a track, run the engine loop once,
        verify the playback state transitions from IDLE to PLAYING.
        """
        ps = self.m.playback  # module-level singleton
        # Reset state
        self._run(ps.stop())
        self.m.init_db()

        rel = str(self._track_path.relative_to(Path(self._tmpdir.name)))
        self.m.db_enqueue(rel, "alice")

        # Run the engine coroutine for a single tick.
        async def single_tick():
            # Simulate what playback_engine does on one iteration when IDLE
            if not ps.is_playing:
                head = self.m.db_dequeue_head()
                if head:
                    abs_path = (self.m.MUSIC_ROOT / head["path"]).resolve()
                    meta = self.m._track_metadata(abs_path)
                    track = {**meta, "nick": head["nick"]}
                    await ps.start_track(track)

        self._run(single_tick())
        self.assertTrue(ps.is_playing, "Expected PLAYING after enqueue, still IDLE")

    def test_queue_advances_after_track_ends(self):
        """
        Start a short track, simulate elapsed reaching duration, verify the
        state transitions back to IDLE (or starts the next track if one exists).
        """
        ps = self.m.playback
        self._run(ps.stop())
        self.m.init_db()

        # Enqueue two tracks
        rel = str(self._track_path.relative_to(Path(self._tmpdir.name)))
        self.m.db_enqueue(rel, "alice")
        self.m.db_enqueue(rel, "bob")

        # Manually start the first track with a very short duration
        track = {
            "path": rel, "title": "Short", "artist": "", "album": "",
            "duration": 1, "nick": "alice",
        }
        self._run(ps.start_track(track))

        # Simulate the engine detecting the track has ended
        async def advance():
            still, elapsed, duration = await ps.tick()
            if duration > 0 and elapsed >= duration:
                await ps.stop()
                head = self.m.db_dequeue_head()
                if head:
                    abs_path = (self.m.MUSIC_ROOT / head["path"]).resolve()
                    meta = self.m._track_metadata(abs_path)
                    next_track = {**meta, "nick": head["nick"]}
                    await ps.start_track(next_track)

        self._run(advance())
        # The second track should now be playing
        self.assertTrue(ps.is_playing, "Expected second track to be PLAYING after first ended")


if __name__ == "__main__":
    unittest.main()
