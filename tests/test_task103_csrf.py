"""
tests/test_task103_csrf.py — Task 1.03 acceptance tests

Verifies CSRF token protection (double-submit cookie pattern):
  - POST /api/admin/services/{id}/start without the X-CSRF-Token header → 403
  - POST /api/admin/services/{id}/start with a matching X-CSRF-Token header
    → proceeds to the handler (not 403)

Note: the service endpoints now also require a valid session (Task 1.07).
These tests supply a valid session cookie where needed to isolate the CSRF
behaviour.  The 403 CSRF cases are tested without a session because the
CSRF check fires before the session dependency when both cookies are absent
— however, once session is present, CSRF is the next gate.  The tests that
check session-less behaviour (no CSRF cookie → 403) are documented below.
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("HEARTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_SECRET = "test-secret-key-for-unit-tests-only"


def _make_session_cookie() -> str:
    """Return a signed session cookie value for the test admin user."""
    return URLSafeTimedSerializer(_SECRET).dumps({"username": "admin"})


class TestTask103CSRF(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Acceptance criterion: POST without CSRF header returns 403
    # (with a valid session so the CSRF check is the failing gate)
    # ------------------------------------------------------------------

    def test_post_without_csrf_header_returns_403(self):
        """Valid session but no CSRF cookie/header → 403."""
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("hearth_session", _make_session_cookie())
        response = client.post("/api/admin/services/chat/start")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF validation failed"})

    def test_post_with_csrf_cookie_but_no_header_returns_403(self):
        """CSRF cookie present but header missing → 403."""
        token = "abc123deadbeef"
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("hearth_session", _make_session_cookie())
        client.cookies.set("csrf_token", token)
        response = client.post("/api/admin/services/chat/start")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "CSRF validation failed"})

    def test_post_with_mismatched_csrf_token_returns_403(self):
        """Cookie and header present but values differ → 403."""
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("hearth_session", _make_session_cookie())
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
        client.cookies.set("hearth_session", _make_session_cookie())
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
        client = TestClient(app)
        response = client.get("/healthz")
        self.assertIn("csrf_token", response.cookies)

    def test_get_request_does_not_replace_existing_csrf_cookie(self):
        """GET should not overwrite a csrf_token cookie that is already set."""
        existing_token = "existing-token-xyz"
        client = TestClient(app)
        client.cookies.set("csrf_token", existing_token)
        response = client.get("/healthz")
        new_cookie = response.cookies.get("csrf_token")
        self.assertIn(new_cookie, (None, existing_token))


if __name__ == "__main__":
    unittest.main()
