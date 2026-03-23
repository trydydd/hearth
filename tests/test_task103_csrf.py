"""
tests/test_task103_csrf.py — Task 1.03 acceptance tests

Verifies CSRF token protection (double-submit cookie pattern):
  - POST /api/admin/services/{id}/start without the X-CSRF-Token header → 403
  - POST /api/admin/services/{id}/start with a matching X-CSRF-Token header
    → proceeds to the handler (not 403)
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


class TestTask103CSRF(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Acceptance criterion: POST without CSRF header returns 403
    # ------------------------------------------------------------------

    def test_post_without_csrf_header_returns_403(self):
        """No CSRF cookie and no header → 403."""
        response = self.client.post("/api/admin/services/chat/start")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF validation failed"})

    def test_post_with_csrf_cookie_but_no_header_returns_403(self):
        """CSRF cookie present but header missing → 403."""
        token = "abc123deadbeef"
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("csrf_token", token)
        response = client.post("/api/admin/services/chat/start")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF validation failed"})

    def test_post_with_mismatched_csrf_token_returns_403(self):
        """Cookie and header present but values differ → 403."""
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("csrf_token", "correct-token")
        response = client.post(
            "/api/admin/services/chat/start",
            headers={"X-CSRF-Token": "wrong-token"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF validation failed"})

    # ------------------------------------------------------------------
    # Acceptance criterion: POST with matching header proceeds to handler
    # ------------------------------------------------------------------

    def test_post_with_matching_csrf_token_proceeds(self):
        """Matching cookie and header → CSRF check passes (not 403)."""
        token = "valid-csrf-token-abcdef123456"
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("csrf_token", token)
        response = client.post(
            "/api/admin/services/chat/start",
            headers={"X-CSRF-Token": token},
        )
        self.assertNotEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # CSRF cookie is issued on GET requests
    # ------------------------------------------------------------------

    def test_get_request_sets_csrf_cookie_when_absent(self):
        """GET /healthz should set a csrf_token cookie when none is present."""
        # Use a fresh client with no existing cookies
        client = TestClient(app)
        response = client.get("/healthz")
        self.assertIn("csrf_token", response.cookies)

    def test_get_request_does_not_replace_existing_csrf_cookie(self):
        """GET should not overwrite a csrf_token cookie that is already set."""
        existing_token = "existing-token-xyz"
        client = TestClient(app)
        client.cookies.set("csrf_token", existing_token)
        response = client.get("/healthz")
        # Cookie should not be replaced
        new_cookie = response.cookies.get("csrf_token")
        self.assertIn(new_cookie, (None, existing_token))


if __name__ == "__main__":
    unittest.main()
