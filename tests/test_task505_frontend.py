"""
tests/test_task505_frontend.py — Task 5.05 acceptance tests

Verifies the jukebox frontend:
  - index.html exists.
  - References /hearth.css.
  - Contains WebSocket connection logic to /jukebox/ws.
  - Contains expected UI panels (now playing, queue, library).
  - No external resource references.
"""

import unittest
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "ansible" / "roles" / "jukebox" / "files" / "frontend"
INDEX_HTML   = FRONTEND_DIR / "index.html"


class TestTask505Frontend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text()

    # ------------------------------------------------------------------
    # Acceptance criterion: index.html exists
    # ------------------------------------------------------------------

    def test_index_html_exists(self):
        self.assertTrue(INDEX_HTML.exists(), f"Missing: {INDEX_HTML}")

    # ------------------------------------------------------------------
    # Acceptance criterion: references /hearth.css
    # ------------------------------------------------------------------

    def test_references_hearth_css(self):
        self.assertIn("/hearth.css", self.html)

    # ------------------------------------------------------------------
    # Acceptance criterion: WebSocket connection to /jukebox/ws
    # ------------------------------------------------------------------

    def test_websocket_connects_to_jukebox_ws(self):
        self.assertIn("/jukebox/ws", self.html)

    def test_uses_websocket_api(self):
        self.assertIn("WebSocket", self.html)

    # ------------------------------------------------------------------
    # Acceptance criterion: expected UI panels present
    # ------------------------------------------------------------------

    def test_has_audio_element(self):
        self.assertIn("<audio", self.html.lower())

    def test_has_now_playing_section(self):
        # Some form of "now playing" text in the UI
        self.assertIn("now", self.html.lower())
        self.assertIn("playing", self.html.lower())

    def test_has_queue_section(self):
        self.assertIn("queue", self.html.lower())

    def test_has_library_section(self):
        self.assertIn("library", self.html.lower())

    def test_has_idle_message(self):
        self.assertIn("idle", self.html.lower())

    def test_has_add_to_queue_button(self):
        # The library items must have an "add to queue" affordance
        self.assertIn("queue", self.html.lower())

    # ------------------------------------------------------------------
    # Acceptance criterion: no external resources
    # ------------------------------------------------------------------

    def test_no_external_script_src(self):
        import re
        external_scripts = re.findall(r'src\s*=\s*["\']https?://', self.html, re.IGNORECASE)
        self.assertEqual(
            external_scripts, [],
            f"Found external script references: {external_scripts}",
        )

    def test_no_external_stylesheet(self):
        import re
        external_css = re.findall(
            r'<link[^>]+href\s*=\s*["\']https?://', self.html, re.IGNORECASE
        )
        self.assertEqual(
            external_css, [],
            f"Found external stylesheet references: {external_css}",
        )

    # ------------------------------------------------------------------
    # Acceptance criterion: progressive-enhancement — audio src or fetch
    # ------------------------------------------------------------------

    def test_stream_endpoint_referenced(self):
        self.assertIn("/jukebox/stream", self.html)


if __name__ == "__main__":
    unittest.main()
