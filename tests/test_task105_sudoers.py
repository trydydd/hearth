"""
tests/test_task105_sudoers.py — Task 1.05 acceptance tests

Verifies the sudoers template and Ansible task:
  - Rendered sudoers file contains only expected systemctl commands.
  - No blanket ALL grants.
  - visudo -c -f passes (if visudo is available in the test environment).

Also verifies the cafebox-admin user / service-unit setup required for PAM
password verification to work at runtime:
  - cafebox-admin must be in the ``shadow`` group (common role).
  - The systemd service unit must declare SupplementaryGroups=shadow.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SUDOERS_TEMPLATE = (
    REPO_ROOT / "ansible" / "roles" / "admin" / "templates" / "sudoers-cafebox.j2"
)
TASKS_MAIN = REPO_ROOT / "ansible" / "roles" / "admin" / "tasks" / "main.yml"
COMMON_TASKS = REPO_ROOT / "ansible" / "roles" / "common" / "tasks" / "main.yml"
SERVICE_UNIT = (
    REPO_ROOT / "ansible" / "roles" / "admin" / "templates" / "cafebox-admin.service.j2"
)

# The template is static (no Jinja2 variables); read it directly as the
# rendered content.
RENDERED = SUDOERS_TEMPLATE.read_text()


class TestTask105Sudoers(unittest.TestCase):
    # ------------------------------------------------------------------
    # Files exist
    # ------------------------------------------------------------------

    def test_sudoers_template_exists(self):
        self.assertTrue(SUDOERS_TEMPLATE.exists())

    def test_tasks_main_references_sudoers_template(self):
        tasks = TASKS_MAIN.read_text()
        self.assertIn("sudoers-cafebox.j2", tasks)

    def test_tasks_main_creates_cafebox_admin_user(self):
        tasks = TASKS_MAIN.read_text()
        self.assertIn("cafebox-admin", tasks)

    # ------------------------------------------------------------------
    # Acceptance criterion: only expected systemctl commands
    # ------------------------------------------------------------------

    def test_contains_start_stop_restart_for_all_services(self):
        expected_units = [
            "conduit.service",
            "element-web.service",
            "calibre-web.service",
            "kiwix.service",
            "navidrome.service",
        ]
        for unit in expected_units:
            with self.subTest(unit=unit):
                self.assertIn(f"systemctl start {unit}", RENDERED)
                self.assertIn(f"systemctl stop {unit}", RENDERED)
                self.assertIn(f"systemctl restart {unit}", RENDERED)

    def test_assigns_to_cafebox_admin_user(self):
        self.assertIn("cafebox-admin", RENDERED)

    def test_uses_nopasswd(self):
        self.assertIn("NOPASSWD", RENDERED)

    # ------------------------------------------------------------------
    # Acceptance criterion: no blanket ALL grants
    # ------------------------------------------------------------------

    def test_no_blanket_all_grant(self):
        """There must be no line granting ALL=(ALL) ALL or similar."""
        import re
        # Match patterns like "ALL=(ALL) ALL" or "ALL = ALL" — blanket grants
        blanket_pattern = re.compile(
            r'ALL\s*=\s*\(?\s*ALL\s*\)?\s+ALL',
            re.IGNORECASE,
        )
        # Strip comment lines before checking
        non_comment_lines = [
            line for line in RENDERED.splitlines()
            if not line.lstrip().startswith("#") and line.strip()
        ]
        non_comment_content = "\n".join(non_comment_lines)
        self.assertIsNone(
            blanket_pattern.search(non_comment_content),
            "Sudoers file must not contain blanket ALL grants",
        )

    def test_only_systemctl_commands(self):
        """Every Cmnd_Alias line must reference only systemctl."""
        for line in RENDERED.splitlines():
            stripped = line.strip()
            # Lines that specify commands (contain /bin/ or /usr/bin/)
            if stripped.startswith("/bin/") or stripped.startswith("/usr/bin/"):
                self.assertIn(
                    "systemctl",
                    stripped,
                    f"Unexpected non-systemctl command in sudoers: {stripped}",
                )

    # ------------------------------------------------------------------
    # Optional: visudo syntax check (skipped if visudo not available)
    # ------------------------------------------------------------------

    def test_visudo_syntax_check(self):
        try:
            result = subprocess.run(
                ["which", "visudo"], capture_output=True
            )
            if result.returncode != 0:
                self.skipTest("visudo not available in this environment")
        except FileNotFoundError:
            self.skipTest("visudo not available in this environment")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".sudoers", delete=False
        ) as tmp:
            tmp.write(RENDERED)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["visudo", "-c", "-f", tmp_path],
                capture_output=True,
                text=True,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"visudo reported errors:\n{result.stdout}\n{result.stderr}",
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestCafeboxAdminShadowGroup(unittest.TestCase):
    """Verify that the common role grants cafebox-admin shadow group access.

    Without shadow group membership the admin backend process cannot read
    /etc/shadow, which means spwd.getspnam() raises PermissionError and
    verify_password() always returns False — causing every login attempt to
    return 401 regardless of the password.
    """

    def setUp(self):
        self.common_tasks = COMMON_TASKS.read_text()

    def test_common_tasks_adds_shadow_group(self):
        """cafebox-admin user task must include the shadow group."""
        self.assertIn("shadow", self.common_tasks)

    def test_common_tasks_appends_groups(self):
        """Group membership must use append: true to preserve primary group."""
        self.assertIn("append: true", self.common_tasks)

    def test_common_tasks_does_not_lock_password(self):
        """password_lock: true must not be set — it would re-lock the account
        on re-provision, breaking logins after first-boot sets the password."""
        self.assertNotIn("password_lock: true", self.common_tasks)


class TestCafeboxAdminServiceUnit(unittest.TestCase):
    """Verify the systemd service unit exposes the shadow group to the process.

    Declaring SupplementaryGroups=shadow in the service unit ensures the
    backend process inherits shadow group access even when NoNewPrivileges=true
    prevents setgid helpers from elevating.
    """

    def setUp(self):
        self.service_unit = SERVICE_UNIT.read_text()

    def test_service_unit_has_supplementary_groups_shadow(self):
        self.assertIn("SupplementaryGroups=shadow", self.service_unit)

    def test_service_unit_runs_as_cafebox_admin(self):
        self.assertIn("User=cafebox-admin", self.service_unit)


if __name__ == "__main__":
    unittest.main()
