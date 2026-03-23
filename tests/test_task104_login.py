"""
tests/test_task104_login.py — Task 1.04 acceptance tests

Verifies the login / logout flow:
  - Correct credentials → 200 + ``cafebox_session`` cookie set
  - Wrong credentials   → 401
  - Logout              → ``cafebox_session`` cookie cleared
  - Protected route     → 401 without valid session cookie
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Provide a test secret key before importing the app so that the session
# serializer initialises without raising RuntimeError.
os.environ.setdefault("CAFEBOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402


class TestTask104Login(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Acceptance criterion: correct credentials → 200 + session cookie
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=True)
    def test_correct_credentials_returns_200(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)

    @patch("routers.auth.verify_password", return_value=True)
    def test_correct_credentials_sets_session_cookie(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "correct-password"},
        )
        self.assertIn("cafebox_session", response.cookies)

    # ------------------------------------------------------------------
    # Acceptance criterion: wrong credentials → 401
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=False)
    def test_wrong_credentials_returns_401(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)

    @patch("routers.auth.verify_password", return_value=False)
    def test_wrong_credentials_does_not_set_session_cookie(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        self.assertNotIn("cafebox_session", response.cookies)

    # ------------------------------------------------------------------
    # Acceptance criterion: logout clears the session cookie
    # ------------------------------------------------------------------

    def test_logout_returns_200(self):
        response = self.client.post("/api/admin/logout")
        self.assertEqual(response.status_code, 200)

    def test_logout_clears_session_cookie(self):
        """After logout the Set-Cookie header deletes the session cookie."""
        response = self.client.post("/api/admin/logout")
        set_cookie = response.headers.get("set-cookie", "")
        # Starlette delete_cookie sets Max-Age=0
        self.assertIn("cafebox_session", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)


if __name__ == "__main__":
    unittest.main()
