"""
tests/test_task106_public_api.py — Task 1.06 acceptance tests

Verifies GET /api/public/services/status:
  - Response matches the documented JSON shape.
  - A disabled service appears with "enabled": false.
  - Endpoint is accessible without authentication.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("HEARTH_SECRET_KEY", "test-secret-key-for-unit-tests-only")

import routers.public as public_router  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_SAMPLE_CONFIG = {
    "box": {"domain": "hearth.home"},
    "services": {
        "chat": {"enabled": True, "registration_token": "", "max_request_size": 20000000},
        "calibre_web": {"enabled": True},
        "kiwix": {"enabled": False},
        "music": {"enabled": True},
    },
    "storage": {"locations": {}},
}


class TestTask106PublicAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app, raise_server_exceptions=False)

    def _get_status(self, first_boot: bool = False, cfg: dict = _SAMPLE_CONFIG):
        with (
            patch.object(public_router, "_is_first_boot", return_value=first_boot),
            patch("config.load_config", return_value=cfg),
        ):
            return self.client.get("/api/public/services/status")

    # ------------------------------------------------------------------
    # Acceptance criterion: response matches documented shape
    # ------------------------------------------------------------------

    def test_response_is_200(self):
        response = self._get_status()
        self.assertEqual(response.status_code, 200)

    def test_response_has_first_boot_key(self):
        response = self._get_status(first_boot=True)
        self.assertIn("first_boot", response.json())
        self.assertTrue(response.json()["first_boot"])

    def test_response_has_services_list(self):
        response = self._get_status()
        data = response.json()
        self.assertIn("services", data)
        self.assertIsInstance(data["services"], list)

    def test_each_service_has_required_fields(self):
        response = self._get_status()
        for svc in response.json()["services"]:
            with self.subTest(svc=svc.get("id")):
                self.assertIn("id", svc)
                self.assertIn("name", svc)
                self.assertIn("enabled", svc)

    # ------------------------------------------------------------------
    # Acceptance criterion: disabled services appear with enabled: false
    # ------------------------------------------------------------------

    def test_disabled_service_has_enabled_false(self):
        response = self._get_status()
        services = {s["id"]: s for s in response.json()["services"]}
        self.assertFalse(services["kiwix"]["enabled"])

    def test_enabled_service_has_enabled_true(self):
        response = self._get_status()
        services = {s["id"]: s for s in response.json()["services"]}
        self.assertTrue(services["chat"]["enabled"])
        self.assertTrue(services["music"]["enabled"])

    def test_enabled_service_has_url(self):
        response = self._get_status()
        services = {s["id"]: s for s in response.json()["services"]}
        self.assertIsNotNone(services["chat"]["url"])
        self.assertIn("hearth.home", services["chat"]["url"])

    def test_disabled_service_has_no_url(self):
        response = self._get_status()
        services = {s["id"]: s for s in response.json()["services"]}
        self.assertIsNone(services["kiwix"]["url"])

    # ------------------------------------------------------------------
    # Acceptance criterion: endpoint accessible without authentication
    # ------------------------------------------------------------------

    def test_accessible_without_auth_cookie(self):
        """No session cookie → still returns 200 (public endpoint)."""
        with (
            patch.object(public_router, "_is_first_boot", return_value=False),
            patch("config.load_config", return_value=_SAMPLE_CONFIG),
        ):
            response = self.client.get("/api/public/services/status")
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # first_boot flag reflects marker file
    # ------------------------------------------------------------------

    def test_first_boot_true_when_marker_exists(self):
        fd, marker_path_str = tempfile.mkstemp(suffix=".pw")
        marker_path = Path(marker_path_str)
        os.write(fd, b"TestPassXyz1\n")
        os.close(fd)
        old = public_router._FIRST_BOOT_MARKER
        public_router._FIRST_BOOT_MARKER = marker_path
        try:
            with patch("config.load_config", return_value=_SAMPLE_CONFIG):
                response = self.client.get("/api/public/services/status")
            self.assertTrue(response.json()["first_boot"])
        finally:
            public_router._FIRST_BOOT_MARKER = old
            marker_path.unlink(missing_ok=True)

    def test_first_boot_false_when_marker_absent(self):
        absent_path = Path("/tmp/hearth-test-absent-marker-xyz")
        absent_path.unlink(missing_ok=True)
        old = public_router._FIRST_BOOT_MARKER
        public_router._FIRST_BOOT_MARKER = absent_path
        try:
            with patch("config.load_config", return_value=_SAMPLE_CONFIG):
                response = self.client.get("/api/public/services/status")
            self.assertFalse(response.json()["first_boot"])
        finally:
            public_router._FIRST_BOOT_MARKER = old

    def test_initial_password_included_when_first_boot(self):
        """Response includes initial_password when the marker file exists."""
        fd, marker_path_str = tempfile.mkstemp(suffix=".pw")
        marker_path = Path(marker_path_str)
        os.write(fd, b"SecretPass99\n")
        os.close(fd)
        old = public_router._FIRST_BOOT_MARKER
        public_router._FIRST_BOOT_MARKER = marker_path
        try:
            with patch("config.load_config", return_value=_SAMPLE_CONFIG):
                response = self.client.get("/api/public/services/status")
            data = response.json()
            self.assertIn("initial_password", data)
            self.assertEqual(data["initial_password"], "SecretPass99")
        finally:
            public_router._FIRST_BOOT_MARKER = old
            marker_path.unlink(missing_ok=True)

    def test_initial_password_absent_when_not_first_boot(self):
        """Response must not include initial_password after first-boot is done."""
        absent_path = Path("/tmp/hearth-test-absent-marker-xyz")
        absent_path.unlink(missing_ok=True)
        old = public_router._FIRST_BOOT_MARKER
        public_router._FIRST_BOOT_MARKER = absent_path
        try:
            with patch("config.load_config", return_value=_SAMPLE_CONFIG):
                response = self.client.get("/api/public/services/status")
            self.assertNotIn("initial_password", response.json())
        finally:
            public_router._FIRST_BOOT_MARKER = old


if __name__ == "__main__":
    unittest.main()
