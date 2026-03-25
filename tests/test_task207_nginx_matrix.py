"""
tests/test_task207_nginx_matrix.py — Task 2.07 acceptance tests

Verifies the nginx configuration template additions for Matrix + Element Web:
  - Rendered config contains /_matrix/ location block.
  - Rendered config contains /.well-known/matrix/ location blocks.
  - Rendered config contains /element/ location block.
  - client_max_body_size is set in the /_matrix/ block.
  - Matrix blocks are absent when services.chat.enabled is false.
  - Rendered config passes nginx -t (if nginx is available).
"""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
NGINX_TEMPLATE_DIR = REPO_ROOT / "ansible" / "roles" / "nginx" / "templates"
CAFE_YAML = REPO_ROOT / "cafe.yaml"


def _render(chat_enabled: bool = True) -> str:
    with CAFE_YAML.open() as fh:
        cfg = yaml.safe_load(fh)

    services = dict(cfg.get("services", {}))
    services["chat"] = {
        "enabled": chat_enabled,
        "registration_token": "",
        "max_request_size": 20000000,
    }

    env = Environment(
        loader=FileSystemLoader(str(NGINX_TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    return env.get_template("nginx.conf.j2").render(
        box=cfg.get("box", {}),
        services=services,
        nginx_conf_dest="/etc/nginx/sites-enabled/cafebox",
    )


def _server_block(rendered: str) -> str:
    """Return only the server{} block, stripping the comment header."""
    idx = rendered.find("\nserver {")
    return rendered[idx:] if idx != -1 else rendered


class TestTask207NginxMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered_enabled = _render(chat_enabled=True)
        cls.rendered_disabled = _render(chat_enabled=False)
        cls.server_enabled = _server_block(cls.rendered_enabled)
        cls.server_disabled = _server_block(cls.rendered_disabled)

    # ------------------------------------------------------------------
    # Acceptance criterion: /_matrix/ location block present when enabled
    # ------------------------------------------------------------------

    def test_matrix_location_present_when_enabled(self):
        self.assertIn("location /_matrix/", self.server_enabled)

    def test_matrix_proxies_to_conduit(self):
        match = re.search(
            r"location\s+/_matrix/\s*\{([^}]*)\}",
            self.server_enabled,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "No location /_matrix/ block found")
        self.assertIn("proxy_pass http://127.0.0.1:6167", match.group(1))

    def test_matrix_location_has_body_size_limit(self):
        match = re.search(
            r"location\s+/_matrix/\s*\{([^}]*)\}",
            self.server_enabled,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "No location /_matrix/ block found")
        self.assertIn("client_max_body_size", match.group(1))

    # ------------------------------------------------------------------
    # Acceptance criterion: /.well-known/matrix/ blocks present
    # ------------------------------------------------------------------

    def test_well_known_matrix_server_present(self):
        self.assertIn("/.well-known/matrix/server", self.server_enabled)

    def test_well_known_matrix_client_present(self):
        self.assertIn("/.well-known/matrix/client", self.server_enabled)

    def test_well_known_server_returns_correct_json_shape(self):
        """/.well-known/matrix/server response must contain m.server key."""
        self.assertIn("m.server", self.server_enabled)

    def test_well_known_client_returns_correct_json_shape(self):
        """/.well-known/matrix/client response must contain m.homeserver key."""
        self.assertIn("m.homeserver", self.server_enabled)

    # ------------------------------------------------------------------
    # Acceptance criterion: /element/ static location present
    # ------------------------------------------------------------------

    def test_element_location_present_when_enabled(self):
        self.assertIn("location /element/", self.server_enabled)

    def test_element_serves_from_install_dir(self):
        self.assertIn("/srv/cafebox/element-web/", self.server_enabled)

    # ------------------------------------------------------------------
    # Acceptance criterion: Matrix blocks absent when chat disabled
    # ------------------------------------------------------------------

    def test_matrix_location_absent_when_disabled(self):
        self.assertNotIn("location /_matrix/", self.server_disabled)

    def test_element_location_absent_when_disabled(self):
        self.assertNotIn("location /element/", self.server_disabled)

    def test_well_known_absent_when_disabled(self):
        self.assertNotIn("/.well-known/matrix/", self.server_disabled)

    # ------------------------------------------------------------------
    # No /_synapse/ route (Synapse-specific, not used with Conduit)
    # ------------------------------------------------------------------

    def test_no_synapse_location(self):
        self.assertNotIn("/_synapse/", self.server_enabled)

    # ------------------------------------------------------------------
    # nginx -t syntax check
    # ------------------------------------------------------------------

    def test_nginx_config_syntax_chat_enabled(self):
        self._nginx_t(self.rendered_enabled)

    def test_nginx_config_syntax_chat_disabled(self):
        self._nginx_t(self.rendered_disabled)

    def _nginx_t(self, rendered: str):
        try:
            result = subprocess.run(["which", "nginx"], capture_output=True)
            if result.returncode != 0:
                self.skipTest("nginx not available in this environment")
        except FileNotFoundError:
            self.skipTest("nginx not available in this environment")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as tmp:
            tmp.write("events {}\nhttp {\n")
            tmp.write(rendered)
            tmp.write("\n}\n")
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["nginx", "-t", "-c", tmp_path],
                capture_output=True,
                text=True,
            )
            combined = (result.stdout + result.stderr).lower()
            self.assertIn("syntax is ok", combined)
            self.assertNotIn("syntax error", combined)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
