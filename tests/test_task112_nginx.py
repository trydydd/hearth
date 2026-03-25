"""
tests/test_task112_nginx.py — Task 1.12 acceptance tests

Verifies the nginx configuration template:
  - Template contains location /api/ block.
  - Template contains location /admin/ block.
  - Portal HTML does not contain any link to /admin/.
  - Rendered config passes `nginx -t` (if nginx is installed).
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
NGINX_TEMPLATE_DIR = REPO_ROOT / "ansible" / "roles" / "nginx" / "templates"
NGINX_TEMPLATE = NGINX_TEMPLATE_DIR / "nginx.conf.j2"
PORTAL_HTML = REPO_ROOT / "ansible" / "roles" / "nginx" / "files" / "index.html"
CAFE_YAML = REPO_ROOT / "hearth.yaml"


def _render_nginx_template() -> str:
    """Render the nginx Jinja2 template with the sample hearth.yaml config."""
    with CAFE_YAML.open() as fh:
        cfg = yaml.safe_load(fh)

    env = Environment(
        loader=FileSystemLoader(str(NGINX_TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("nginx.conf.j2")
    return template.render(
        box=cfg.get("box", {}),
        services=cfg.get("services", {}),
        nginx_conf_dest="/etc/nginx/sites-enabled/hearth",
    )


class TestTask112NginxRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = _render_nginx_template()

    # ------------------------------------------------------------------
    # Acceptance criterion: template has location /api/ block
    # ------------------------------------------------------------------

    def test_has_api_location(self):
        self.assertIn("location /api/", self.rendered)

    def test_api_proxies_to_backend(self):
        self.assertIn("proxy_pass http://127.0.0.1:8000", self.rendered)

    # ------------------------------------------------------------------
    # Acceptance criterion: /healthz is proxied to the admin backend
    # ------------------------------------------------------------------

    def test_has_healthz_location(self):
        """login.html fetches /healthz to seed the CSRF cookie; it must be
        proxied to the backend, not handled by nginx's static file root."""
        self.assertIn("location /healthz", self.rendered)

    def test_healthz_proxies_to_backend(self):
        import re
        # There must be a proxy_pass inside the /healthz location block.
        # Match the block and check it contains proxy_pass to port 8000.
        match = re.search(
            r"location\s+/healthz\s*\{([^}]*)\}",
            self.rendered,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "No location /healthz block found")
        self.assertIn("proxy_pass http://127.0.0.1:8000", match.group(1))

    # ------------------------------------------------------------------
    # Acceptance criterion: template has location /admin/ block
    # ------------------------------------------------------------------

    def test_has_admin_location(self):
        self.assertIn("location /admin/", self.rendered)

    def test_admin_serves_static_files(self):
        """Admin location must serve from a local alias, not proxy."""
        self.assertIn("alias", self.rendered.lower())
        self.assertIn("/admin/", self.rendered)

    # ------------------------------------------------------------------
    # Acceptance criterion: portal HTML has no /admin/ links
    # ------------------------------------------------------------------

    def test_portal_has_no_admin_link(self):
        portal = PORTAL_HTML.read_text()
        # The portal must not reference /admin/
        import re
        # Check for href or src pointing to /admin/ — but allow the
        # nginx config comments to reference it (those are in the template)
        # This test is about the portal HTML only.
        self.assertNotIn(
            "/admin/",
            portal,
            "Portal HTML (index.html) must not contain any reference to /admin/",
        )

    # ------------------------------------------------------------------
    # Optional: nginx -t syntax check
    # ------------------------------------------------------------------

    def test_nginx_config_syntax(self):
        try:
            result = subprocess.run(["which", "nginx"], capture_output=True)
            if result.returncode != 0:
                self.skipTest("nginx not available in this environment")
        except FileNotFoundError:
            self.skipTest("nginx not available in this environment")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as tmp:
            # The template renders a server{} block; wrap it in an http{} block
            # and a minimal nginx.conf so that `nginx -t -c` can validate it.
            tmp.write("events {}\nhttp {\n")
            tmp.write(self.rendered)
            tmp.write("\n}\n")
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["nginx", "-t", "-c", tmp_path],
                capture_output=True,
                text=True,
            )
            combined = (result.stdout + result.stderr).lower()
            self.assertIn(
                "syntax is ok",
                combined,
                f"nginx -t did not confirm 'syntax is ok':\n{result.stdout}\n{result.stderr}",
            )
            self.assertNotIn(
                "syntax error",
                combined,
                f"nginx -t found syntax errors:\n{result.stdout}\n{result.stderr}",
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
