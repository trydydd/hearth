"""
tests/test_task109_login_html.py — Task 1.09 acceptance tests

Verifies login.html:
  - Contains a <form> element.
  - Form has properly labelled inputs (label for= matches input id=).
  - No external resource references (no CDN, no external src/href).
"""

import sys
import unittest
import re
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOGIN_HTML = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "frontend" / "login.html"


class _ExternalResourceChecker(HTMLParser):
    """Collect src/href/action attributes that point to external resources."""

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


class TestTask109LoginHTML(unittest.TestCase):
    def setUp(self):
        self.content = LOGIN_HTML.read_text()

    # ------------------------------------------------------------------
    # Acceptance criterion: file exists
    # ------------------------------------------------------------------

    def test_login_html_exists(self):
        self.assertTrue(LOGIN_HTML.exists(), "login.html must exist")

    # ------------------------------------------------------------------
    # Acceptance criterion: contains <form> element
    # ------------------------------------------------------------------

    def test_contains_form_element(self):
        self.assertIn("<form", self.content.lower())

    # ------------------------------------------------------------------
    # Acceptance criterion: labels are associated with inputs
    # ------------------------------------------------------------------

    def test_username_input_has_label(self):
        # id="username" must exist and a label for="username" must exist
        self.assertIn('id="username"', self.content)
        self.assertIn('for="username"', self.content)

    def test_password_input_has_label(self):
        self.assertIn('id="password"', self.content)
        self.assertIn('for="password"', self.content)

    def test_username_input_is_type_text_or_text(self):
        self.assertRegex(self.content, r'type=["\']text["\']|type=["\']email["\']')

    def test_password_input_is_type_password(self):
        self.assertIn('type="password"', self.content)

    # ------------------------------------------------------------------
    # Acceptance criterion: no external resources loaded
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
    # Page functionality: sends to the correct API endpoint
    # ------------------------------------------------------------------

    def test_references_login_api(self):
        self.assertIn("/api/admin/login", self.content)

    def test_references_dashboard_redirect(self):
        self.assertIn("dashboard.html", self.content)


if __name__ == "__main__":
    unittest.main()
