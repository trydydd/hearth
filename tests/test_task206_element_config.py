"""
tests/test_task206_element_config.py — Task 2.06 acceptance tests

Verifies the Element Web config.json template:
  - Rendered config.json is valid JSON.
  - base_url contains no hardcoded domains.
  - All required keys are present (default_server_config, brand,
    disable_guests, roomDirectory).
"""

import json
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "ansible" / "roles" / "element_web" / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "element-web-config.json.j2"
CAFE_YAML = REPO_ROOT / "cafe.yaml"


def _render(domain: str = "cafe.box", box_name: str = "CafeBox") -> str:
    with CAFE_YAML.open() as fh:
        cfg = yaml.safe_load(fh)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    return env.get_template("element-web-config.json.j2").render(
        box={"domain": domain, "name": box_name},
        services=cfg.get("services", {}),
    )


class TestTask206ElementConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = _render()
        cls.parsed = json.loads(cls.rendered)

    # ------------------------------------------------------------------
    # Acceptance criterion: template file exists
    # ------------------------------------------------------------------

    def test_template_file_exists(self):
        self.assertTrue(TEMPLATE_FILE.is_file(), f"Template not found: {TEMPLATE_FILE}")

    # ------------------------------------------------------------------
    # Acceptance criterion: rendered output is valid JSON
    # ------------------------------------------------------------------

    def test_renders_to_valid_json(self):
        try:
            json.loads(self.rendered)
        except json.JSONDecodeError as exc:
            self.fail(f"Rendered config.json is not valid JSON: {exc}")

    # ------------------------------------------------------------------
    # Acceptance criterion: all required keys present
    # ------------------------------------------------------------------

    def test_default_server_config_present(self):
        self.assertIn("default_server_config", self.parsed)

    def test_homeserver_base_url_present(self):
        dsc = self.parsed["default_server_config"]
        self.assertIn("m.homeserver", dsc)
        self.assertIn("base_url", dsc["m.homeserver"])

    def test_brand_present(self):
        self.assertIn("brand", self.parsed)
        self.assertEqual(self.parsed["brand"], "CafeBox")

    def test_disable_guests_present(self):
        self.assertIn("disable_guests", self.parsed)

    def test_room_directory_present(self):
        self.assertIn("roomDirectory", self.parsed)
        self.assertIn("servers", self.parsed["roomDirectory"])

    # ------------------------------------------------------------------
    # Acceptance criterion: no hardcoded domains in template
    # ------------------------------------------------------------------

    def test_base_url_contains_no_hardcoded_domain(self):
        """base_url must use box.domain, not a literal domain string."""
        template_text = TEMPLATE_FILE.read_text()
        # The template must not contain literal domain strings
        for literal in ("cafe.box", "matrix.cafe.box", "localhost"):
            self.assertNotIn(
                literal,
                template_text,
                f"Template must not hardcode '{literal}' — use {{ box.domain }} instead",
            )

    def test_base_url_contains_rendered_domain(self):
        """Rendered base_url must contain the domain from cafe.yaml."""
        base_url = self.parsed["default_server_config"]["m.homeserver"]["base_url"]
        self.assertIn("cafe.box", base_url)

    def test_room_directory_contains_rendered_domain(self):
        """roomDirectory.servers must contain the rendered domain."""
        servers = self.parsed["roomDirectory"]["servers"]
        self.assertIn("cafe.box", servers)

    # ------------------------------------------------------------------
    # Acceptance criterion: brand reflects box.name
    # ------------------------------------------------------------------

    def test_brand_uses_box_name(self):
        rendered = _render(box_name="MyCafe")
        parsed = json.loads(rendered)
        self.assertEqual(parsed["brand"], "MyCafe")


if __name__ == "__main__":
    unittest.main()
