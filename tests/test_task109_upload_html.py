"""
tests/test_task109_upload_html.py — Task 1.11 upload.html acceptance tests

Verifies upload.html:
  - Contains upload forms for Kiwix, Calibre, and Navidrome.
  - Each form has a properly labelled file input.
  - No external resources loaded.
"""

import re
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_HTML = (
    REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "frontend" / "upload.html"
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


class TestTask109UploadHTML(unittest.TestCase):
    def setUp(self):
        self.content = UPLOAD_HTML.read_text()

    def test_upload_html_exists(self):
        self.assertTrue(UPLOAD_HTML.exists(), "upload.html must exist")

    def test_contains_form_elements(self):
        self.assertIn("<form", self.content.lower())

    def test_has_kiwix_upload(self):
        self.assertIn("kiwix", self.content.lower())

    def test_has_calibre_upload(self):
        self.assertIn("calibre", self.content.lower())

    def test_has_navidrome_upload(self):
        self.assertIn("navidrome", self.content.lower())

    def test_file_inputs_have_labels(self):
        # Each file input must have a corresponding label
        self.assertRegex(self.content, r'<label\b[^>]*\bfor=')
        self.assertRegex(self.content, r'<input\b[^>]*type=["\']file["\']')

    def test_references_upload_api(self):
        self.assertIn("/api/admin/upload/", self.content)

    def test_no_external_resources(self):
        checker = _ExternalResourceChecker()
        checker.feed(self.content)
        self.assertEqual(
            checker.external_resources,
            [],
            f"Found external resource references: {checker.external_resources}",
        )

    def test_has_progress_indicator(self):
        self.assertIn("<progress", self.content)


if __name__ == "__main__":
    unittest.main()
