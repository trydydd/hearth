"""
tests/test_task104_login.py — Task 1.04 acceptance tests

Verifies the login / logout flow:
  - Correct credentials → 200 + ``hearth_session`` cookie set
  - Wrong credentials   → 401
  - Logout              → ``hearth_session`` cookie cleared
  - Protected route     → 401 without valid session cookie
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import call, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Provide a test secret key before importing the app so that the session
# serialiser initialises without raising RuntimeError.
os.environ.setdefault("HEARTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
import routers.auth as auth_router  # noqa: E402


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
            json={"username": "hearth-admin", "password": "correct-password"},
        )
        self.assertEqual(response.status_code, 200)

    @patch("routers.auth.verify_password", return_value=True)
    def test_correct_credentials_sets_session_cookie(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "hearth-admin", "password": "correct-password"},
        )
        self.assertIn("hearth_session", response.cookies)

    # ------------------------------------------------------------------
    # Acceptance criterion: wrong credentials → 401
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=False)
    def test_wrong_credentials_returns_401(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "hearth-admin", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)

    @patch("routers.auth.verify_password", return_value=False)
    def test_wrong_credentials_does_not_set_session_cookie(self, _mock):
        response = self.client.post(
            "/api/admin/login",
            json={"username": "hearth-admin", "password": "wrong-password"},
        )
        self.assertNotIn("hearth_session", response.cookies)

    # ------------------------------------------------------------------
    # Acceptance criterion: backend always authenticates as hearth-admin
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=True)
    def test_login_always_authenticates_as_hearth_admin(self, mock_vp):
        """Even if the form submits username='admin', auth uses hearth-admin."""
        self.client.post(
            "/api/admin/login",
            json={"username": "admin", "password": "correct-password"},
        )
        mock_vp.assert_called_once_with(auth_router._ADMIN_USER, "correct-password")

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
        self.assertIn("hearth_session", set_cookie)
        self.assertIn("Max-Age=0", set_cookie)


class TestVerifyPasswordPython313Compat(unittest.TestCase):
    """Verify that auth.py does not reference crypt or spwd.

    Both modules were removed in Python 3.13 (PEP 594).  Raspberry Pi OS
    Trixie (Debian 13) ships Python 3.13, so any import of crypt or spwd
    would cause verify_password() to silently return False on every call,
    regardless of the password set on the system account.
    """

    def setUp(self):
        import re
        auth_path = BACKEND_DIR / "auth.py"
        self.auth_source = auth_path.read_text()
        # Match only real import statements, not comments or docstrings.
        self._import_re = re.compile(
            r"^\s*(import\s+(crypt|spwd)|from\s+(crypt|spwd)\s+import)",
            re.MULTILINE,
        )

    def test_auth_does_not_import_crypt(self):
        matches = [
            m.group(0).strip()
            for m in self._import_re.finditer(self.auth_source)
            if "crypt" in m.group(0)
        ]
        self.assertEqual(
            matches,
            [],
            "auth.py must not import 'crypt' — removed in Python 3.13: " + str(matches),
        )

    def test_auth_does_not_import_spwd(self):
        matches = [
            m.group(0).strip()
            for m in self._import_re.finditer(self.auth_source)
            if "spwd" in m.group(0)
        ]
        self.assertEqual(
            matches,
            [],
            "auth.py must not import 'spwd' — removed in Python 3.13: " + str(matches),
        )


class TestRequirementsTxtIncludesPam(unittest.TestCase):
    """Verify that requirements.txt lists python-pam.

    The admin backend runs inside an isolated virtualenv.  The ``python3-pam``
    apt package is only visible to the *system* Python, not to the virtualenv.
    If ``python-pam`` is absent from requirements.txt the pip-install step will
    skip it, ``import pam`` will raise ImportError at runtime, and
    ``verify_password()`` will always return False — causing every login attempt
    to fail with 401 regardless of the correct password.
    """

    def setUp(self):
        req_path = BACKEND_DIR / "requirements.txt"
        self.requirements = req_path.read_text()

    def test_python_pam_in_requirements(self):
        import re
        # Accept 'python-pam' with any version specifier or none.
        self.assertIsNotNone(
            re.search(r"^\s*python-pam\b", self.requirements, re.MULTILINE | re.IGNORECASE),
            "requirements.txt must include python-pam so PAM auth works inside the virtualenv",
        )


if __name__ == "__main__":
    unittest.main()
