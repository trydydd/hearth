"""
tests/test_task501_jukebox_scaffold.py — Task 5.01 acceptance tests

Verifies the jukebox service scaffold:
  - hearth-jukebox.service unit file exists and contains required directives.
  - Ansible tasks file enables hearth-jukebox.service.
  - GET /jukebox/health returns {"status": "ok"}.
  - GET /jukebox/queue returns [] on a fresh start.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parents[1]
SERVICE_FILE = REPO_ROOT / "ansible" / "roles" / "jukebox" / "files" / "hearth-jukebox.service"
TASKS_FILE   = REPO_ROOT / "ansible" / "roles" / "jukebox" / "tasks" / "main.yml"
SERVER_DIR   = REPO_ROOT / "ansible" / "roles" / "jukebox" / "files" / "server"


class TestTask501ServiceUnit(unittest.TestCase):
    """Service unit file structure and hardening directives."""

    def test_service_file_exists(self):
        self.assertTrue(SERVICE_FILE.exists(), f"Missing: {SERVICE_FILE}")

    def test_service_contains_readonly_paths(self):
        content = SERVICE_FILE.read_text()
        self.assertIn("ReadOnlyPaths=/srv/hearth/music", content)

    def test_service_contains_readwrite_tmp(self):
        content = SERVICE_FILE.read_text()
        self.assertIn("ReadWritePaths=/tmp", content)

    def test_service_runs_on_port_8766(self):
        content = SERVICE_FILE.read_text()
        self.assertIn("8766", content)

    def test_service_has_private_tmp(self):
        content = SERVICE_FILE.read_text()
        self.assertIn("PrivateTmp=true", content)

    def test_service_user_is_hearth_jukebox(self):
        content = SERVICE_FILE.read_text()
        self.assertIn("User=hearth-jukebox", content)


class TestTask501TasksFile(unittest.TestCase):
    """Ansible tasks enable the service."""

    def test_tasks_file_exists(self):
        self.assertTrue(TASKS_FILE.exists(), f"Missing: {TASKS_FILE}")

    def test_tasks_enable_service(self):
        content = TASKS_FILE.read_text()
        self.assertIn("hearth-jukebox.service", content)
        self.assertIn("enabled: true", content)


class TestTask501RequirementsFile(unittest.TestCase):
    """requirements.txt contains all specified packages."""

    def test_requirements_file_exists(self):
        req = SERVER_DIR / "requirements.txt"
        self.assertTrue(req.exists(), f"Missing: {req}")

    def test_requirements_contains_fastapi(self):
        content = (SERVER_DIR / "requirements.txt").read_text()
        self.assertIn("fastapi", content.lower())

    def test_requirements_contains_mutagen(self):
        content = (SERVER_DIR / "requirements.txt").read_text()
        self.assertIn("mutagen", content.lower())

    def test_requirements_contains_aiofiles(self):
        content = (SERVER_DIR / "requirements.txt").read_text()
        self.assertIn("aiofiles", content.lower())

    def test_requirements_contains_uvicorn(self):
        content = (SERVER_DIR / "requirements.txt").read_text()
        self.assertIn("uvicorn", content.lower())


class TestTask501JukeboxApp(unittest.TestCase):
    """HTTP endpoint behaviour on a fresh instance."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls._dbfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls._dbfile.close()

        os.environ["HEARTH_MUSIC_ROOT"] = cls._tmpdir.name
        os.environ["HEARTH_JUKEBOX_DB"] = cls._dbfile.name

        # Import after setting env vars so module-level globals pick them up.
        if str(SERVER_DIR) not in sys.path:
            sys.path.insert(0, str(SERVER_DIR))

        # Force reimport in case another test loaded it with different paths.
        for mod in list(sys.modules.keys()):
            if mod in ("main",):
                del sys.modules[mod]

        from fastapi.testclient import TestClient
        import main as jukebox_main
        # Initialise the DB manually (lifespan may not run without context manager)
        jukebox_main.init_db()
        cls.client = TestClient(jukebox_main.app)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()
        Path(cls._dbfile.name).unlink(missing_ok=True)

    def test_health_returns_ok(self):
        response = self.client.get("/jukebox/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_queue_returns_empty_list_on_fresh_start(self):
        response = self.client.get("/jukebox/queue")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
