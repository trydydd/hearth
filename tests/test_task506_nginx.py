"""
tests/test_task506_nginx.py — Task 5.06 acceptance tests

Verifies nginx configuration for the jukebox service:
  - Rendered config contains all four location blocks when
    services.music.enabled: true.
  - All four blocks are absent when services.music.enabled: false.
  - jukebox role is listed in ansible/site.yml.
"""

import copy
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT          = Path(__file__).resolve().parents[1]
NGINX_TEMPLATE_DIR = REPO_ROOT / "ansible" / "roles" / "nginx" / "templates"
NGINX_TEMPLATE     = NGINX_TEMPLATE_DIR / "nginx.conf.j2"
HEARTH_YAML        = REPO_ROOT / "hearth.yaml"
SITE_YML           = REPO_ROOT / "ansible" / "site.yml"


def _render(services_override: dict) -> str:
    with HEARTH_YAML.open() as fh:
        cfg = yaml.safe_load(fh)
    cfg["services"] = services_override

    env = Environment(
        loader=FileSystemLoader(str(NGINX_TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    template = env.get_template("nginx.conf.j2")
    return template.render(
        box=cfg.get("box", {}),
        services=cfg["services"],
        nginx_conf_dest="/etc/nginx/sites-enabled/hearth",
    )


_MUSIC_ENABLED  = {"music": {"enabled": True}}
_MUSIC_DISABLED = {"music": {"enabled": False}}


class TestTask506NginxJukeboxBlocks(unittest.TestCase):
    """All four location blocks present when music.enabled: true."""

    @classmethod
    def setUpClass(cls):
        cls.rendered_on  = _render(_MUSIC_ENABLED)
        cls.rendered_off = _render(_MUSIC_DISABLED)

    # ------------------------------------------------------------------
    # Acceptance criterion: four location blocks when enabled
    # ------------------------------------------------------------------

    def test_redirect_block_present_when_enabled(self):
        self.assertIn("location = /jukebox", self.rendered_on)
        self.assertIn("return 301 /jukebox/", self.rendered_on)

    def test_ws_proxy_block_present_when_enabled(self):
        self.assertIn("location /jukebox/ws", self.rendered_on)
        self.assertIn("proxy_pass", self.rendered_on)
        self.assertIn("8766", self.rendered_on)

    def test_stream_proxy_block_present_when_enabled(self):
        self.assertIn("location /jukebox/stream", self.rendered_on)
        self.assertIn("proxy_buffering", self.rendered_on.lower())

    def test_static_frontend_block_present_when_enabled(self):
        self.assertIn("location /jukebox/", self.rendered_on)
        self.assertIn("/var/www/hearth/jukebox", self.rendered_on)

    def test_websocket_upgrade_headers_present(self):
        self.assertIn("Upgrade", self.rendered_on)
        self.assertIn("Connection", self.rendered_on)

    # ------------------------------------------------------------------
    # Acceptance criterion: blocks absent when disabled
    # ------------------------------------------------------------------

    def test_redirect_block_absent_when_disabled(self):
        self.assertNotIn("return 301 /jukebox/", self.rendered_off)

    def test_ws_proxy_absent_when_disabled(self):
        self.assertNotIn("location /jukebox/ws", self.rendered_off)

    def test_stream_proxy_absent_when_disabled(self):
        self.assertNotIn("location /jukebox/stream", self.rendered_off)

    def test_static_frontend_absent_when_disabled(self):
        self.assertNotIn("/var/www/hearth/jukebox", self.rendered_off)


class TestTask506SiteYml(unittest.TestCase):
    """jukebox role is included in ansible/site.yml."""

    def test_jukebox_role_in_site_yml(self):
        with SITE_YML.open() as fh:
            content = fh.read()
        self.assertIn("jukebox", content)

    def test_site_yml_is_valid_yaml(self):
        with SITE_YML.open() as fh:
            parsed = yaml.safe_load(fh)
        self.assertIsNotNone(parsed)

    def test_jukebox_in_roles_list(self):
        with SITE_YML.open() as fh:
            parsed = yaml.safe_load(fh)
        raw_roles = parsed[0].get("roles", [])
        roles = [r["role"] if isinstance(r, dict) else r for r in raw_roles]
        self.assertIn("jukebox", roles, f"'jukebox' not found in roles list: {roles}")


if __name__ == "__main__":
    unittest.main()
