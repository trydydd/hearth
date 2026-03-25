"""
tests/test_task204_conduit_service.py — Task 2.04 acceptance tests

Verifies the Conduit systemd service unit:
  - Service unit file exists.
  - Contains Restart=on-failure, PrivateTmp=true, NoNewPrivileges=true.
  - tasks/main.yml creates the conduit user and enables the service.
"""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONDUIT_ROLE = REPO_ROOT / "ansible" / "roles" / "conduit"
SERVICE_FILE = CONDUIT_ROLE / "files" / "conduit.service"
TASKS_FILE = CONDUIT_ROLE / "tasks" / "main.yml"


class TestTask204ConduitService(unittest.TestCase):
    # ------------------------------------------------------------------
    # Acceptance criterion: service unit file exists
    # ------------------------------------------------------------------

    def test_service_file_exists(self):
        self.assertTrue(SERVICE_FILE.is_file(), f"Service unit not found: {SERVICE_FILE}")

    # ------------------------------------------------------------------
    # Acceptance criterion: required hardening directives present
    # ------------------------------------------------------------------

    def test_restart_on_failure(self):
        text = SERVICE_FILE.read_text()
        self.assertIn("Restart=on-failure", text)

    def test_private_tmp(self):
        text = SERVICE_FILE.read_text()
        self.assertIn("PrivateTmp=true", text)

    def test_no_new_privileges(self):
        text = SERVICE_FILE.read_text()
        self.assertIn("NoNewPrivileges=true", text)

    def test_runs_as_conduit_user(self):
        text = SERVICE_FILE.read_text()
        self.assertIn("User=conduit", text)

    # ------------------------------------------------------------------
    # Acceptance criterion: tasks/main.yml creates conduit user
    # ------------------------------------------------------------------

    def test_tasks_create_conduit_user(self):
        tasks = yaml.safe_load(TASKS_FILE.read_text()) or []
        user_tasks = [
            t for t in tasks
            if isinstance(t, dict) and (
                "ansible.builtin.user" in t or "user" in t
            )
        ]
        self.assertTrue(
            len(user_tasks) > 0,
            "tasks/main.yml must contain a user task to create the conduit system user",
        )
        # At least one user task must reference 'conduit'
        found = any(
            "conduit" in str(t.get("ansible.builtin.user", t.get("user", {})))
            for t in user_tasks
        )
        self.assertTrue(found, "A user task must create the 'conduit' system user")

    # ------------------------------------------------------------------
    # Acceptance criterion: tasks/main.yml enables the service
    # ------------------------------------------------------------------

    def test_tasks_enable_conduit_service(self):
        tasks = yaml.safe_load(TASKS_FILE.read_text()) or []
        systemd_tasks = [
            t for t in tasks
            if isinstance(t, dict) and (
                "ansible.builtin.systemd" in t or "systemd" in t
            )
        ]
        self.assertTrue(
            len(systemd_tasks) > 0,
            "tasks/main.yml must contain a systemd task to enable conduit.service",
        )
        found = any(
            "conduit" in str(t.get("ansible.builtin.systemd", t.get("systemd", {})))
            for t in systemd_tasks
        )
        self.assertTrue(found, "A systemd task must reference conduit.service")


if __name__ == "__main__":
    unittest.main()
