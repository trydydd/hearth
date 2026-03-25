"""
tests/test_task107_services.py — Task 1.07 acceptance tests

Verifies authenticated service start/stop/restart endpoints:
  - Unknown service_id → 404.
  - systemctl failure → 500 with stderr in the response body.
  - Valid service_id with valid session and CSRF token → 200.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("CAFEBOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_SECRET = "test-secret-key-for-unit-tests-only"
_CSRF_TOKEN = "test-csrf-token-abcdef1234567890"


def _make_session_cookie() -> str:
    return URLSafeTimedSerializer(_SECRET).dumps({"username": "admin"})


def _authed_client() -> TestClient:
    """Return a TestClient with valid session and CSRF cookies pre-set."""
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("cafebox_session", _make_session_cookie())
    client.cookies.set("csrf_token", _CSRF_TOKEN)
    return client


def _post(path: str, **kwargs):
    return _authed_client().post(path, headers={"X-CSRF-Token": _CSRF_TOKEN}, **kwargs)


class TestTask107Services(unittest.TestCase):
    # ------------------------------------------------------------------
    # Acceptance criterion: unknown service_id → 404
    # ------------------------------------------------------------------

    def test_unknown_service_id_returns_404(self):
        response = _post("/api/admin/services/unknown-service/start")
        self.assertEqual(response.status_code, 404)

    def test_unknown_service_id_stop_returns_404(self):
        response = _post("/api/admin/services/doesnotexist/stop")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Acceptance criterion: systemctl failure → 500 with stderr
    # ------------------------------------------------------------------

    def test_systemctl_failure_returns_500_with_stderr(self):
        """When systemctl exits non-zero, return 500 with stderr."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Failed to start calibre-web.service: unit not found"

        with patch("routers.services.subprocess.run", return_value=mock_result):
            response = _post("/api/admin/services/calibre_web/start")

        self.assertEqual(response.status_code, 500)
        self.assertIn("Failed to start", response.json()["detail"])

    # ------------------------------------------------------------------
    # Acceptance criterion: valid request → 200
    # ------------------------------------------------------------------

    def test_valid_start_returns_200(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("routers.services.subprocess.run", return_value=mock_result):
            response = _post("/api/admin/services/calibre_web/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "started")

    def test_valid_stop_returns_200(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("routers.services.subprocess.run", return_value=mock_result):
            response = _post("/api/admin/services/navidrome/stop")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "stopped")

    def test_valid_restart_returns_200(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("routers.services.subprocess.run", return_value=mock_result):
            response = _post("/api/admin/services/kiwix/restart")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "restarted")

    # ------------------------------------------------------------------
    # Correct systemd unit names are used (no shell injection risk)
    # ------------------------------------------------------------------

    def test_subprocess_called_with_list_not_string(self):
        """subprocess.run must receive a list (no shell=True) — no shell injection."""
        captured_calls = []

        def fake_run(cmd, **kwargs):
            captured_calls.append(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        with patch("routers.services.subprocess.run", side_effect=fake_run):
            _post("/api/admin/services/calibre_web/start")

        self.assertTrue(len(captured_calls) > 0)
        cmd = captured_calls[0]
        self.assertIsInstance(cmd, list, "subprocess.run must receive a list, not a string")
        self.assertIn("systemctl", cmd)
        self.assertIn("start", cmd)
        self.assertIn("calibre-web.service", cmd)

    # ------------------------------------------------------------------
    # Requires session — 401 without session cookie
    # ------------------------------------------------------------------

    def test_requires_session(self):
        """Request without session cookie → 401."""
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("csrf_token", _CSRF_TOKEN)
        response = client.post(
            "/api/admin/services/chat/start",
            headers={"X-CSRF-Token": _CSRF_TOKEN},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
