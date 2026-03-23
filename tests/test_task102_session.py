"""
tests/test_task102_session.py — Task 1.02 acceptance tests

Verifies the signed-cookie session middleware:
  - A route protected by require_session returns 401 without a valid cookie.
  - A route protected by require_session returns 200 with a valid session cookie.
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("CAFEBOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from session import require_session, set_session_cookie  # noqa: E402

# Build a minimal test app with one protected route
_test_app = FastAPI()

_SECRET = "test-secret-key-for-unit-tests-only"


@_test_app.get("/protected")
async def protected(session: dict = Depends(require_session)):
    return {"username": session.get("username")}


def _make_session_cookie(username: str = "admin") -> str:
    return URLSafeTimedSerializer(_SECRET).dumps({"username": username})


class TestTask102Session(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(_test_app, raise_server_exceptions=False)

    # ------------------------------------------------------------------
    # Acceptance criterion: protected route returns 401 without cookie
    # ------------------------------------------------------------------

    def test_protected_route_returns_401_without_cookie(self):
        """No session cookie → 401."""
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 401)

    def test_protected_route_returns_401_with_tampered_cookie(self):
        """Tampered cookie → 401."""
        client = TestClient(_test_app, raise_server_exceptions=False)
        client.cookies.set("cafebox_session", "not-a-valid-signed-token")
        response = client.get("/protected")
        self.assertEqual(response.status_code, 401)

    # ------------------------------------------------------------------
    # Acceptance criterion: protected route returns 200 with valid cookie
    # ------------------------------------------------------------------

    def test_protected_route_returns_200_with_valid_cookie(self):
        """Valid signed session cookie → 200."""
        client = TestClient(_test_app, raise_server_exceptions=False)
        client.cookies.set("cafebox_session", _make_session_cookie())
        response = client.get("/protected")
        self.assertEqual(response.status_code, 200)

    def test_protected_route_returns_session_payload(self):
        """Valid cookie → response contains session data."""
        client = TestClient(_test_app, raise_server_exceptions=False)
        client.cookies.set("cafebox_session", _make_session_cookie("operator"))
        response = client.get("/protected")
        self.assertEqual(response.json()["username"], "operator")


if __name__ == "__main__":
    unittest.main()
