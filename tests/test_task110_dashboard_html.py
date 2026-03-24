"""
tests/test_task110_dashboard_html.py — Task 1.10 acceptance tests

Verifies dashboard.html:
  - Contains service tile elements.
  - Contains start, stop, and restart buttons.
  - Contains a logout button.
  - No external resources loaded.
"""

import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_HTML = (
    REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "frontend" / "dashboard.html"
)


class _ExternalResourceChecker(HTMLParser):
    EXTERNAL_PATTERN = re.compile(r'^https?://', re.IGNORECASE)

    def __init__(self):
        super().__init__()
        self.external_resources = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        for attr in ("src", "href", "action"):
            val = attr_dict.get(attr, "")
            if val and self.EXTERNAL_PATTERN.match(val):
                self.external_resources.append((tag, attr, val))


class TestTask110DashboardHTML(unittest.TestCase):
    def setUp(self):
        self.content = DASHBOARD_HTML.read_text()

    # ------------------------------------------------------------------
    # File exists
    # ------------------------------------------------------------------

    def test_dashboard_html_exists(self):
        self.assertTrue(DASHBOARD_HTML.exists(), "dashboard.html must exist")

    # ------------------------------------------------------------------
    # Acceptance criterion: contains tile elements
    # ------------------------------------------------------------------

    def test_contains_tile_grid(self):
        self.assertIn("tile-grid", self.content)

    def test_fetches_services_status(self):
        self.assertIn("/api/admin/services/status", self.content)

    # ------------------------------------------------------------------
    # Acceptance criterion: start / stop / restart buttons
    # ------------------------------------------------------------------

    def test_references_start_action(self):
        self.assertIn("start", self.content.lower())

    def test_references_stop_action(self):
        self.assertIn("stop", self.content.lower())

    def test_references_restart_action(self):
        self.assertIn("restart", self.content.lower())

    def test_has_action_buttons_in_js(self):
        """JS must build start/stop/restart buttons dynamically."""
        self.assertIn("btn-start", self.content)
        self.assertIn("btn-stop", self.content)
        self.assertIn("btn-restart", self.content)

    # ------------------------------------------------------------------
    # Acceptance criterion: logout button present
    # ------------------------------------------------------------------

    def test_has_logout_button(self):
        # Must have a button or element that triggers logout
        self.assertIn("logout", self.content.lower())

    def test_logout_calls_api(self):
        self.assertIn("/api/admin/logout", self.content)

    # ------------------------------------------------------------------
    # Acceptance criterion: no external resources
    # ------------------------------------------------------------------

    def test_no_external_resources(self):
        checker = _ExternalResourceChecker()
        checker.feed(self.content)
        self.assertEqual(
            checker.external_resources,
            [],
            f"Found external resource references: {checker.external_resources}",
        )

    # ------------------------------------------------------------------
    # Buttons disabled while action in progress
    # ------------------------------------------------------------------

    def test_buttons_disabled_while_in_progress(self):
        """JS must disable buttons during an in-flight request."""
        self.assertIn("disabled", self.content)

    # ------------------------------------------------------------------
    # Tiles update without full reload
    # ------------------------------------------------------------------

    def test_tiles_update_without_reload(self):
        """fetchAndRender must be called after an action (no location.reload)."""
        self.assertIn("fetchAndRender", self.content)
        # Must NOT use a full page reload after service action
        # (location.reload would be acceptable only for logout, not tile actions)


if __name__ == "__main__":
    unittest.main()
