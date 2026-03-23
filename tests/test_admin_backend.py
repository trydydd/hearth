"""
tests/test_admin_backend.py — Task 1.01 acceptance tests

Verifies:
  - GET /healthz returns HTTP 200 with body {"status": "ok"}
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "ansible" / "roles" / "admin" / "files" / "backend"

# Make the backend package importable without installing it.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402  (after sys.path tweak)
from main import app  # noqa: E402


class TestTask101AdminBackendSetup(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # ------------------------------------------------------------------
    # Acceptance criterion: GET /healthz returns {"status": "ok"} / 200
    # ------------------------------------------------------------------

    def test_healthz_status_code(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)

    def test_healthz_body(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.json(), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
