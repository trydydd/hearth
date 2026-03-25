"""
tests/test_task208_chat_tile.py — Task 2.08 acceptance tests

Verifies the chat service tile:
  - /api/public/services/status includes the chat tile when enabled.
  - /api/public/services/status omits (enabled: false) when disabled.
  - Chat tile URL points to /element/.
  - Token is NOT exposed via the public API.
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

os.environ.setdefault("CAFEBOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

import routers.public as public_router  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_CFG_ENABLED = {
    "box": {"domain": "cafe.box"},
    "services": {
        "chat": {
            "enabled": True,
            "registration_token": "supersecret",
            "max_request_size": 20000000,
        },
    },
    "storage": {"locations": {}},
}

_CFG_DISABLED = {
    "box": {"domain": "cafe.box"},
    "services": {
        "chat": {
            "enabled": False,
            "registration_token": "supersecret",
            "max_request_size": 20000000,
        },
    },
    "storage": {"locations": {}},
}


def _get_status(cfg: dict) -> dict:
    client = TestClient(app, raise_server_exceptions=False)
    with (
        patch.object(public_router, "_is_first_boot", return_value=False),
        patch("config.load_config", return_value=cfg),
    ):
        resp = client.get("/api/public/services/status")
    assert resp.status_code == 200
    return {s["id"]: s for s in resp.json()["services"]}


class TestTask208ChatTile(unittest.TestCase):
    # ------------------------------------------------------------------
    # Acceptance criterion: chat tile present when enabled
    # ------------------------------------------------------------------

    def test_chat_tile_present_when_enabled(self):
        services = _get_status(_CFG_ENABLED)
        self.assertIn("chat", services)

    def test_chat_tile_enabled_true_when_enabled(self):
        services = _get_status(_CFG_ENABLED)
        self.assertTrue(services["chat"]["enabled"])

    def test_chat_tile_url_points_to_element(self):
        services = _get_status(_CFG_ENABLED)
        url = services["chat"]["url"]
        self.assertIsNotNone(url)
        self.assertIn("/element/", url)

    def test_chat_tile_name_is_chat(self):
        services = _get_status(_CFG_ENABLED)
        self.assertEqual(services["chat"]["name"], "Chat")

    # ------------------------------------------------------------------
    # Acceptance criterion: chat tile disabled when not enabled
    # ------------------------------------------------------------------

    def test_chat_tile_enabled_false_when_disabled(self):
        services = _get_status(_CFG_DISABLED)
        self.assertIn("chat", services)
        self.assertFalse(services["chat"]["enabled"])

    def test_chat_tile_url_none_when_disabled(self):
        services = _get_status(_CFG_DISABLED)
        self.assertIsNone(services["chat"]["url"])

    # ------------------------------------------------------------------
    # Acceptance criterion: registration_token never exposed publicly
    # ------------------------------------------------------------------

    def test_registration_token_not_in_public_response(self):
        """The registration_token must never appear in the public API response."""
        client = TestClient(app, raise_server_exceptions=False)
        with (
            patch.object(public_router, "_is_first_boot", return_value=False),
            patch("config.load_config", return_value=_CFG_ENABLED),
        ):
            resp = client.get("/api/public/services/status")
        body = resp.text
        self.assertNotIn(
            "supersecret",
            body,
            "registration_token must not appear in the public API response",
        )


if __name__ == "__main__":
    unittest.main()
