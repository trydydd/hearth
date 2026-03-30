import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import jinja2
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
ROLE_ROOT = REPO_ROOT / "ansible" / "roles" / "eink"
TEMPLATE_PATH = ROLE_ROOT / "templates" / "hearth-eink.py.j2"

_TEST_BOX = {"name": "TestBox", "domain": "test.local"}


def _render_template(box=_TEST_BOX):
    src = TEMPLATE_PATH.read_text()
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    return env.from_string(src).render(box=box)


# ---------------------------------------------------------------------------
# Structure — filesystem + YAML validity
# ---------------------------------------------------------------------------
class TestEinkRoleStructure(unittest.TestCase):

    def test_role_directory_exists(self):
        self.assertTrue(ROLE_ROOT.is_dir(), f"Missing role directory: {ROLE_ROOT}")

    def test_required_files_present(self):
        expected = [
            "meta/main.yml",
            "defaults/main.yml",
            "tasks/main.yml",
            "handlers/main.yml",
            "templates/hearth-eink.py.j2",
            "templates/hearth-eink.service.j2",
        ]
        for rel in expected:
            with self.subTest(file=rel):
                self.assertTrue((ROLE_ROOT / rel).exists(), f"Missing: {rel}")

    def test_yaml_files_parse(self):
        for yml in ROLE_ROOT.rglob("*.yml"):
            with self.subTest(file=yml.relative_to(REPO_ROOT)):
                try:
                    yaml.safe_load(yml.read_text())
                except yaml.YAMLError as exc:
                    self.fail(f"YAML parse error in {yml}: {exc}")


# ---------------------------------------------------------------------------
# Template rendering — Jinja2 → valid Python with correct values injected
# ---------------------------------------------------------------------------
class TestEinkTemplateRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rendered = _render_template()

    def test_template_renders_valid_python(self):
        try:
            compile(self.rendered, "<hearth-eink.py.j2>", "exec")
        except SyntaxError as exc:
            self.fail(f"Rendered template is not valid Python: {exc}")

    def test_display_name_injected(self):
        self.assertIn('DISPLAY_NAME = "TestBox"', self.rendered)

    def test_display_url_injected(self):
        self.assertIn('DISPLAY_URL  = "test.local"', self.rendered)


# ---------------------------------------------------------------------------
# Display logic — _build_image() and main() with mocked inky hardware
# ---------------------------------------------------------------------------
class TestEinkDisplayLogic(unittest.TestCase):
    """
    inky is not installable in CI (requires Pi GPIO drivers).
    We inject MagicMock stubs into sys.modules before loading the rendered
    script so that 'from inky.auto import auto' resolves without error.
    """

    @classmethod
    def setUpClass(cls):
        # Write rendered script to a temp file (importlib needs a real path)
        cls._tmp = Path(tempfile.mktemp(suffix="_hearth_eink_test.py"))
        cls._tmp.write_text(_render_template())

        # Stub inky modules before import so the module-level code sees them
        cls._mock_inky_mod = MagicMock()
        cls._mock_auto_mod = MagicMock()
        sys.modules.setdefault("inky", cls._mock_inky_mod)
        sys.modules.setdefault("inky.auto", cls._mock_auto_mod)

        # Load the rendered script as a module
        spec = importlib.util.spec_from_file_location("_hearth_eink_test", cls._tmp)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

        # Reusable mock inky instance for _build_image() tests
        cls.mock_inky = MagicMock()
        cls.mock_inky.WIDTH = 212
        cls.mock_inky.HEIGHT = 104
        cls.mock_inky.WHITE = 0
        cls.mock_inky.BLACK = 1

    @classmethod
    def tearDownClass(cls):
        cls._tmp.unlink(missing_ok=True)
        sys.modules.pop("inky", None)
        sys.modules.pop("inky.auto", None)

    # --- _build_image() ---

    def test_build_image_returns_pil_image(self):
        from PIL import Image
        result = self.mod._build_image(self.mock_inky)
        self.assertIsInstance(result, Image.Image)

    def test_build_image_dimensions(self):
        result = self.mod._build_image(self.mock_inky)
        self.assertEqual(result.size, (212, 104))

    # --- main() graceful degradation ---

    def test_main_skips_gracefully_on_hardware_error(self):
        """auto() raises Exception (no display attached) → sys.exit(0)."""
        sys.modules["inky.auto"].auto.side_effect = Exception("no hardware")
        try:
            with self.assertRaises(SystemExit) as cm:
                self.mod.main()
            self.assertEqual(cm.exception.code, 0)
        finally:
            sys.modules["inky.auto"].auto.side_effect = None

    def test_main_skips_gracefully_on_import_error(self):
        """inky not importable (removed from sys.modules) → sys.exit(0)."""
        saved_inky = sys.modules.pop("inky", None)
        saved_auto = sys.modules.pop("inky.auto", None)
        try:
            with self.assertRaises(SystemExit) as cm:
                self.mod.main()
            self.assertEqual(cm.exception.code, 0)
        finally:
            if saved_inky is not None:
                sys.modules["inky"] = saved_inky
            if saved_auto is not None:
                sys.modules["inky.auto"] = saved_auto
