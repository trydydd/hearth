"""
tests/test_task108_password.py — Task 1.08 acceptance tests

Verifies POST /api/admin/auth/change-password:
  - Wrong current password → 403.
  - New password shorter than 12 characters → 422.
  - After successful change, /api/public/services/status returns first_boot: false.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("HEARTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

import routers.auth as auth_router  # noqa: E402
import routers.public as public_router  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_SECRET = "test-secret-key-for-unit-tests-only"
_CSRF_TOKEN = "test-csrf-token-abcdef1234567890"


def _make_session_cookie() -> str:
    return URLSafeTimedSerializer(_SECRET).dumps({"username": "hearth-admin"})


def _authed_client() -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("hearth_session", _make_session_cookie())
    client.cookies.set("csrf_token", _CSRF_TOKEN)
    return client


class TestTask108ChangePassword(unittest.TestCase):
    def _post(self, body: dict):
        return _authed_client().post(
            "/api/admin/auth/change-password",
            json=body,
            headers={"X-CSRF-Token": _CSRF_TOKEN},
        )

    # ------------------------------------------------------------------
    # Acceptance criterion: wrong current password → 403
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=False)
    def test_wrong_current_password_returns_403(self, _mock):
        response = self._post(
            {"current_password": "wrongpassword", "new_password": "newlongpassword!"}
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # Acceptance criterion: new password shorter than 12 chars → 422
    # ------------------------------------------------------------------

    def test_short_new_password_returns_422(self):
        response = self._post(
            {"current_password": "anything", "new_password": "tooshort"}
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("12", response.json()["detail"])

    def test_exactly_12_chars_is_accepted(self):
        """12-character password meets the minimum — should not return 422."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        with (
            patch("routers.auth.verify_password", return_value=True),
            patch("routers.auth.subprocess.run", return_value=mock_result),
        ):
            response = self._post(
                {"current_password": "correct", "new_password": "exactly12chr"}
            )
        self.assertNotEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # Acceptance criterion: after successful change, first_boot → false
    # ------------------------------------------------------------------

    def test_successful_change_removes_first_boot_marker(self):
        """Successful password change deletes the first-boot marker."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            marker_path = Path(tmp.name)

        # Point both the auth router and public router at the same marker
        old_auth = auth_router._FIRST_BOOT_MARKER
        old_public = public_router._FIRST_BOOT_MARKER
        auth_router._FIRST_BOOT_MARKER = marker_path
        public_router._FIRST_BOOT_MARKER = marker_path

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        try:
            with (
                patch("routers.auth.verify_password", return_value=True),
                patch("routers.auth.subprocess.run", return_value=mock_result),
                patch("config.load_config", return_value={"box": {"domain": "hearth.local"}, "services": {}}),
            ):
                # First: confirm first_boot is true before change
                client = _authed_client()
                status_before = client.get("/api/public/services/status")
                self.assertTrue(status_before.json()["first_boot"])

                # Change password
                self._post(
                    {"current_password": "oldpassword123", "new_password": "newlongpassword!"}
                )

                # Now first_boot should be false
                status_after = client.get("/api/public/services/status")
                self.assertFalse(status_after.json()["first_boot"])
        finally:
            auth_router._FIRST_BOOT_MARKER = old_auth
            public_router._FIRST_BOOT_MARKER = old_public
            marker_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # chpasswd receives the correct input
    # ------------------------------------------------------------------

    @patch("routers.auth.verify_password", return_value=True)
    def test_chpasswd_called_with_correct_format(self, _mock):
        captured = []

        def fake_run(cmd, **kwargs):
            captured.append({"cmd": cmd, "input": kwargs.get("input", "")})
            r = MagicMock()
            r.returncode = 0
            r.stderr = ""
            return r

        with patch("routers.auth.subprocess.run", side_effect=fake_run):
            self._post(
                {"current_password": "oldpassword123", "new_password": "mynewpassword1"}
            )

        self.assertTrue(len(captured) > 0)
        call = captured[0]
        self.assertTrue(any("chpasswd" in c for c in call["cmd"]))
        self.assertIn("hearth-admin:mynewpassword1", call["input"])


if __name__ == "__main__":
    unittest.main()
