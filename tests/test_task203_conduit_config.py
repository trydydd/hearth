"""
tests/test_task203_conduit_config.py — Task 2.03 acceptance tests

Verifies the Conduit configuration template:
  - Template renders to valid TOML with sample cafe.yaml.
  - allow_federation is always false in the rendered output.
  - server_name, database_path, allow_registration, max_request_size are present.
  - registration_token is included when set, absent when blank.
"""

import sys
import tomllib
import unittest
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "ansible" / "roles" / "conduit" / "templates"
TEMPLATE_FILE = TEMPLATE_DIR / "conduit.toml.j2"
CAFE_YAML = REPO_ROOT / "cafe.yaml"
CONDUIT_DEFAULTS = REPO_ROOT / "ansible" / "roles" / "conduit" / "defaults" / "main.yml"


def _render(extra_vars: dict | None = None) -> str:
    with CAFE_YAML.open() as fh:
        cfg = yaml.safe_load(fh)
    with CONDUIT_DEFAULTS.open() as fh:
        defaults = yaml.safe_load(fh) or {}

    # Merge defaults into the render context (defaults are role-level vars)
    ctx = {**defaults}
    ctx["box"] = cfg.get("box", {})
    ctx["storage"] = cfg.get("storage", {})
    ctx["services"] = cfg.get("services", {})

    if extra_vars:
        # Allow overriding services for token tests
        for k, v in extra_vars.items():
            ctx[k] = v

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        keep_trailing_newline=True,
    )
    return env.get_template("conduit.toml.j2").render(**ctx)


class TestTask203ConduitConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = _render()
        cls.parsed = tomllib.loads(cls.rendered)

    # ------------------------------------------------------------------
    # Acceptance criterion: template renders to valid TOML
    # ------------------------------------------------------------------

    def test_template_file_exists(self):
        self.assertTrue(TEMPLATE_FILE.is_file(), f"Template not found: {TEMPLATE_FILE}")

    def test_renders_to_valid_toml(self):
        """Rendered output must be parseable by tomllib."""
        try:
            tomllib.loads(self.rendered)
        except tomllib.TOMLDecodeError as exc:
            self.fail(f"Rendered conduit.toml is not valid TOML: {exc}")

    # ------------------------------------------------------------------
    # Acceptance criterion: allow_federation is always false
    # ------------------------------------------------------------------

    def test_allow_federation_is_false(self):
        """allow_federation must be hardcoded false — offline-only server."""
        self.assertIn("allow_federation", self.parsed["global"])
        self.assertFalse(
            self.parsed["global"]["allow_federation"],
            "allow_federation must be false regardless of operator config",
        )

    # ------------------------------------------------------------------
    # Acceptance criterion: required settings are present
    # ------------------------------------------------------------------

    def test_server_name_set_to_domain(self):
        self.assertIn("server_name", self.parsed["global"])
        self.assertEqual(self.parsed["global"]["server_name"], "cafe.box")

    def test_database_path_set(self):
        self.assertIn("database_path", self.parsed["global"])
        self.assertTrue(len(self.parsed["global"]["database_path"]) > 0)

    def test_allow_registration_is_true(self):
        self.assertIn("allow_registration", self.parsed["global"])
        self.assertTrue(self.parsed["global"]["allow_registration"])

    def test_max_request_size_present(self):
        self.assertIn("max_request_size", self.parsed["global"])
        self.assertIsInstance(self.parsed["global"]["max_request_size"], int)

    # ------------------------------------------------------------------
    # Acceptance criterion: registration_token included only when set
    # ------------------------------------------------------------------

    def test_registration_token_absent_when_blank(self):
        """When registration_token is blank, it must not appear in rendered TOML."""
        services = {"chat": {"enabled": True, "registration_token": "", "max_request_size": 20000000}}
        rendered = _render({"services": services})
        parsed = tomllib.loads(rendered)
        self.assertNotIn(
            "registration_token",
            parsed["global"],
            "registration_token must be absent when blank",
        )

    def test_registration_token_present_when_set(self):
        """When registration_token is set, it must appear in rendered TOML."""
        services = {"chat": {"enabled": True, "registration_token": "opensesame", "max_request_size": 20000000}}
        rendered = _render({"services": services})
        parsed = tomllib.loads(rendered)
        self.assertIn("registration_token", parsed["global"])
        self.assertEqual(parsed["global"]["registration_token"], "opensesame")


if __name__ == "__main__":
    unittest.main()
