"""
tests/test_task111_upload.py — Task 1.11 acceptance tests

Verifies POST /api/admin/upload/{service_id}:
  - Upload to unknown service_id → 404.
  - .exe upload → rejected with a clear 422 error.
  - Valid file upload → success (200 with filename in response).
"""

import io
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

os.environ.setdefault("CAFEBOX_SECRET_KEY", "test-secret-key-for-unit-tests-only")

from itsdangerous import URLSafeTimedSerializer  # noqa: E402

import routers.upload as upload_router  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402

_SECRET = "test-secret-key-for-unit-tests-only"
_CSRF_TOKEN = "test-csrf-token-abcdef1234567890"


def _make_session_cookie() -> str:
    return URLSafeTimedSerializer(_SECRET).dumps({"username": "admin"})


def _authed_client() -> TestClient:
    client = TestClient(app, raise_server_exceptions=False)
    client.cookies.set("cafebox_session", _make_session_cookie())
    client.cookies.set("csrf_token", _CSRF_TOKEN)
    return client


def _upload(service_id: str, filename: str, content: bytes = b"test data"):
    """Helper: upload a file to the given service_id."""
    client = _authed_client()
    return client.post(
        f"/api/admin/upload/{service_id}",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        headers={"X-CSRF-Token": _CSRF_TOKEN},
    )


class TestTask111Upload(unittest.TestCase):
    # ------------------------------------------------------------------
    # Acceptance criterion: unknown service_id → 404
    # ------------------------------------------------------------------

    def test_unknown_service_id_returns_404(self):
        response = _upload("doesnotexist", "test.zim")
        self.assertEqual(response.status_code, 404)

    def test_conduit_has_no_upload_support_returns_404(self):
        """conduit is not in UPLOAD_EXTENSIONS → 404."""
        response = _upload("conduit", "test.bin")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Acceptance criterion: .exe upload → rejected with clear 422
    # ------------------------------------------------------------------

    def test_exe_upload_returns_422(self):
        response = _upload("kiwix", "malware.exe")
        self.assertEqual(response.status_code, 422)
        self.assertIn("exe", response.json()["detail"].lower())

    def test_disallowed_extension_for_navidrome_returns_422(self):
        response = _upload("navidrome", "video.avi")
        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------------
    # Acceptance criterion: valid file upload → success
    # ------------------------------------------------------------------

    def test_valid_kiwix_upload_returns_200(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "storage": {"locations": {"kiwix": tmpdir}},
            }
            with patch("config.load_config", return_value=cfg):
                response = _upload("kiwix", "wikipedia.zim", b"ZIM file data")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["filename"], "wikipedia.zim")
        self.assertGreater(data["bytes_written"], 0)

    def test_valid_navidrome_upload_returns_200(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "storage": {"locations": {"navidrome": tmpdir}},
            }
            with patch("config.load_config", return_value=cfg):
                response = _upload("navidrome", "song.mp3", b"ID3 fake data")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_valid_calibre_upload_returns_200(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "storage": {"locations": {"calibre_web": tmpdir}},
            }
            with patch("config.load_config", return_value=cfg):
                response = _upload("calibre_web", "book.epub", b"EPUB data")

        self.assertEqual(response.status_code, 200)

    def test_file_is_actually_written_to_disk(self):
        """Uploaded file content must be present on the filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = {
                "storage": {"locations": {"kiwix": tmpdir}},
            }
            content = b"ZIM file test content 12345"
            with patch("config.load_config", return_value=cfg):
                _upload("kiwix", "test.zim", content)

            written = (Path(tmpdir) / "test.zim").read_bytes()
            self.assertEqual(written, content)

    # ------------------------------------------------------------------
    # Requires session — 401 without session cookie
    # ------------------------------------------------------------------

    def test_requires_session(self):
        client = TestClient(app, raise_server_exceptions=False)
        client.cookies.set("csrf_token", _CSRF_TOKEN)
        response = client.post(
            "/api/admin/upload/kiwix",
            files={"file": ("test.zim", io.BytesIO(b"data"), "application/octet-stream")},
            headers={"X-CSRF-Token": _CSRF_TOKEN},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
