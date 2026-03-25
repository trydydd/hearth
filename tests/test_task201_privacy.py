"""
tests/test_task201_privacy.py — Task 2.01 acceptance tests

Verifies the E2EE / Ephemerality Policy deliverables:
  - PRIVACY.md exists and contains the required sections.
  - Privacy notice string is present in index.html.
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVACY_MD = REPO_ROOT / "ansible" / "roles" / "conduit" / "files" / "PRIVACY.md"
PORTAL_HTML = REPO_ROOT / "ansible" / "roles" / "nginx" / "files" / "index.html"


class TestTask201Privacy(unittest.TestCase):
    # ------------------------------------------------------------------
    # Acceptance criterion: PRIVACY.md exists
    # ------------------------------------------------------------------

    def test_privacy_md_exists(self):
        self.assertTrue(PRIVACY_MD.is_file(), f"PRIVACY.md not found at {PRIVACY_MD}")

    # ------------------------------------------------------------------
    # Acceptance criterion: PRIVACY.md contains required sections
    # ------------------------------------------------------------------

    def test_privacy_md_covers_message_persistence(self):
        """PRIVACY.md must explain that messages persist on the box."""
        text = PRIVACY_MD.read_text()
        self.assertTrue(
            any(kw in text.lower() for kw in ("stored", "persist", "not automatically deleted")),
            "PRIVACY.md must explain that messages are stored and not automatically deleted",
        )

    def test_privacy_md_covers_e2ee(self):
        """PRIVACY.md must explain E2EE and what it protects against."""
        text = PRIVACY_MD.read_text()
        self.assertTrue(
            any(kw in text.lower() for kw in ("encrypt", "e2ee", "encryption")),
            "PRIVACY.md must explain end-to-end encryption",
        )

    def test_privacy_md_covers_operator_access(self):
        """PRIVACY.md must explain who can read messages without encryption."""
        text = PRIVACY_MD.read_text()
        self.assertTrue(
            any(kw in text.lower() for kw in ("operator", "access")),
            "PRIVACY.md must explain operator access to unencrypted messages",
        )

    def test_privacy_md_covers_offline(self):
        """PRIVACY.md must note that chat is offline-only."""
        text = PRIVACY_MD.read_text()
        self.assertTrue(
            any(kw in text.lower() for kw in ("offline", "no internet", "never leave")),
            "PRIVACY.md must mention that chat is offline / no internet",
        )

    # ------------------------------------------------------------------
    # Acceptance criterion: privacy notice visible in portal HTML
    # ------------------------------------------------------------------

    def test_portal_html_contains_privacy_notice(self):
        """index.html must contain a one-sentence chat privacy notice."""
        html = PORTAL_HTML.read_text()
        self.assertIn(
            "chat-privacy-notice",
            html,
            "index.html must contain an element with class 'chat-privacy-notice'",
        )

    def test_portal_privacy_notice_mentions_encryption(self):
        """The privacy notice in index.html must mention encryption."""
        html = PORTAL_HTML.read_text()
        self.assertTrue(
            "encrypt" in html.lower(),
            "The privacy notice in index.html must mention encryption",
        )


if __name__ == "__main__":
    unittest.main()
