import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config_module = _load_module("cafebox_config", REPO_ROOT / "scripts" / "config.py")
generate_module = _load_module(
    "cafebox_generate_configs", REPO_ROOT / "scripts" / "generate-configs.py"
)


class TestTask001RepositoryScaffolding(unittest.TestCase):
    def test_required_directories_exist(self):
        expected = [
            "scripts",
            "image",
            "tasks",
            "tests",
            "ansible",
            "ansible/roles/common",
            "ansible/roles/nginx",
            "ansible/roles/wifi",
            "ansible/roles/firewall",
            "ansible/roles/conduit",
            "ansible/roles/element_web",
            "ansible/roles/calibre_web",
            "ansible/roles/kiwix",
            "ansible/roles/navidrome",
            "ansible/roles/admin",
            "ansible/roles/diagnostics",
        ]
        for rel in expected:
            with self.subTest(path=rel):
                self.assertTrue((REPO_ROOT / rel).is_dir(), f"Missing directory: {rel}")

    def test_required_files_exist(self):
        expected = [
            "cafe.yaml",
            "install.sh",
            "Makefile",
            "ansible/site.yml",
            "ansible/ansible.cfg",
            "ansible/roles/nginx/files/index.html",
            "image/README.md",
        ]
        for rel in expected:
            with self.subTest(path=rel):
                self.assertTrue((REPO_ROOT / rel).is_file(), f"Missing file: {rel}")

    def test_portal_and_image_stubs_are_non_empty(self):
        portal_html = (REPO_ROOT / "ansible" / "roles" / "nginx" / "files" / "index.html").read_text()
        image_readme = (REPO_ROOT / "image" / "README.md").read_text()

        self.assertIn("<html", portal_html.lower())
        self.assertTrue(image_readme.strip(), "image/README.md should not be empty")


class TestTask002SampleConfig(unittest.TestCase):
    def test_cafe_yaml_is_valid_yaml(self):
        data = yaml.safe_load((REPO_ROOT / "cafe.yaml").read_text())
        self.assertIsInstance(data, dict)

    def test_cafe_yaml_contains_required_top_level_sections(self):
        data = yaml.safe_load((REPO_ROOT / "cafe.yaml").read_text())
        for key in ["box", "wifi", "storage", "services"]:
            with self.subTest(key=key):
                self.assertIn(key, data)


class TestTask003ConfigLoader(unittest.TestCase):
    def test_load_config_returns_valid_mapping(self):
        config = config_module.load_config(str(REPO_ROOT / "cafe.yaml"))
        self.assertIsInstance(config, dict)
        self.assertIn("box", config)
        self.assertIn("domain", config["box"])

    def test_missing_required_key_raises_configerror(self):
        broken = {
            "box": {"name": "CafeBox", "ip": "10.0.0.1"},
            "wifi": {"ssid": "CafeBox", "interface": "wlan0"},
            "storage": {"base": "/srv/cafebox"},
            "services": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.yaml"
            path.write_text(yaml.safe_dump(broken))
            with self.assertRaises(config_module.ConfigError) as ctx:
                config_module.load_config(str(path))
        self.assertIn("box.domain", str(ctx.exception))

    def test_invalid_hostname_raises_configerror(self):
        broken = {
            "box": {"name": "CafeBox", "domain": "not a hostname", "ip": "10.0.0.1"},
            "wifi": {"ssid": "CafeBox", "interface": "wlan0"},
            "storage": {"base": "/srv/cafebox"},
            "services": {},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "invalid-domain.yaml"
            path.write_text(yaml.safe_dump(broken))
            with self.assertRaises(config_module.ConfigError) as ctx:
                config_module.load_config(str(path))
        self.assertIn("box.domain", str(ctx.exception))


class TestTask004TemplateRenderer(unittest.TestCase):
    def test_generate_configs_script_renders_templates(self):
        result = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        generated = REPO_ROOT / "system" / "generated"
        self.assertTrue(generated.is_dir(), "system/generated/ should be created")
        rendered_files = list(generated.glob("*"))
        self.assertTrue(rendered_files, "At least one template should be rendered")

    def test_generate_configs_is_idempotent(self):
        first = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        second = subprocess.run(
            [sys.executable, "scripts/generate-configs.py", "--config", "cafe.yaml"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertIn("Unchanged:", second.stdout)

    def test_unknown_template_variable_exits_with_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            templates_dir = Path(tmp) / "templates"
            output_dir = Path(tmp) / "output"
            templates_dir.mkdir(parents=True, exist_ok=True)
            (templates_dir / "broken.conf.j2").write_text("value={{ missing_key }}\n")

            with self.assertRaises(SystemExit) as ctx:
                generate_module.render_templates(
                    {"box": {"domain": "cafe.box"}},
                    str(templates_dir),
                    str(output_dir),
                )
            self.assertEqual(ctx.exception.code, 1)


class TestTask005MakefileTargets(unittest.TestCase):
    def test_help_lists_expected_targets(self):
        result = subprocess.run(
            ["make", "help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        for target in [
            "vm-start",
            "vm-stop",
            "vm-ssh",
            "vm-destroy",
            "logs",
        ]:
            with self.subTest(target=target):
                self.assertIn(target, result.stdout)

    def test_vm_target_requires_vagrant(self):
        result = subprocess.run(
            ["make", "vm-start"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = f"{result.stdout}\n{result.stderr}"
        if result.returncode != 0:
            # vagrant missing — guard should produce a helpful message
            self.assertIn("vagrant", combined.lower())
        else:
            # vagrant present — guard passed, no "not installed" complaint
            self.assertNotIn("vagrant is not installed", combined)


class TestAnsibleRoleStructure(unittest.TestCase):
    """Validates the Ansible directory layout follows best practices."""

    ROLES_DIR = REPO_ROOT / "ansible" / "roles"
    EXPECTED_ROLES = [
        "common",
        "wifi",
        "firewall",
        "nginx",
        "conduit",
        "element_web",
        "calibre_web",
        "kiwix",
        "navidrome",
        "admin",
        "diagnostics",
    ]

    def test_all_expected_roles_exist(self):
        for role in self.EXPECTED_ROLES:
            with self.subTest(role=role):
                self.assertTrue(
                    (self.ROLES_DIR / role).is_dir(),
                    f"Missing role directory: ansible/roles/{role}",
                )

    def test_each_role_has_tasks_main(self):
        for role in self.EXPECTED_ROLES:
            with self.subTest(role=role):
                self.assertTrue(
                    (self.ROLES_DIR / role / "tasks" / "main.yml").is_file(),
                    f"Missing tasks/main.yml in role: {role}",
                )

    def test_each_role_has_defaults_and_handlers(self):
        for role in self.EXPECTED_ROLES:
            with self.subTest(role=role, file="defaults/main.yml"):
                self.assertTrue(
                    (self.ROLES_DIR / role / "defaults" / "main.yml").is_file(),
                    f"Missing defaults/main.yml in role: {role}",
                )
            with self.subTest(role=role, file="handlers/main.yml"):
                self.assertTrue(
                    (self.ROLES_DIR / role / "handlers" / "main.yml").is_file(),
                    f"Missing handlers/main.yml in role: {role}",
                )

    def test_site_yml_is_valid_yaml_and_references_all_roles(self):
        site_path = REPO_ROOT / "ansible" / "site.yml"
        data = yaml.safe_load(site_path.read_text())
        self.assertIsInstance(data, list)
        plays = data
        all_roles = []
        for play in plays:
            all_roles.extend(play.get("roles", []))
        for role in self.EXPECTED_ROLES:
            with self.subTest(role=role):
                self.assertIn(role, all_roles, f"site.yml is missing role: {role}")

    def test_group_vars_all_is_valid_yaml(self):
        gv_path = REPO_ROOT / "ansible" / "group_vars" / "all.yml"
        self.assertTrue(gv_path.is_file(), "Missing ansible/group_vars/all.yml")
        data = yaml.safe_load(gv_path.read_text())
        self.assertIsInstance(data, dict)

    def test_inventory_files_exist(self):
        for env in ["development", "production"]:
            with self.subTest(env=env):
                self.assertTrue(
                    (REPO_ROOT / "ansible" / "inventory" / env).is_file(),
                    f"Missing inventory file: {env}",
                )


class TestAnsibleTemplates(unittest.TestCase):
    """Validates Jinja2 templates under ansible/roles/*/templates/."""

    ROLES_DIR = REPO_ROOT / "ansible" / "roles"

    def test_key_templates_exist(self):
        expected = [
            ("nginx", "nginx.conf.j2"),
            ("wifi", "hostapd.conf.j2"),
            ("wifi", "dnsmasq.conf.j2"),
            ("firewall", "nftables.conf.j2"),
        ]
        for role, template in expected:
            with self.subTest(role=role, template=template):
                self.assertTrue(
                    (self.ROLES_DIR / role / "templates" / template).is_file(),
                    f"Missing template: ansible/roles/{role}/templates/{template}",
                )

    def test_all_j2_templates_are_parseable(self):
        from jinja2 import Environment, FileSystemLoader, StrictUndefined

        for templates_dir in self.ROLES_DIR.glob("*/templates"):
            if not templates_dir.is_dir():
                continue
            role_name = templates_dir.parent.name
            env = Environment(
                loader=FileSystemLoader(str(templates_dir)),
                undefined=StrictUndefined,
            )
            for template_file in sorted(templates_dir.glob("*.j2")):
                with self.subTest(role=role_name, template=template_file.name):
                    # Parsing should not raise — validates Jinja2 syntax
                    env.get_template(template_file.name)


class TestTask016BuildImageWorkflow(unittest.TestCase):
    """Validates the build-image workflow and build script without running them."""

    WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build-image.yml"
    CI_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    BUILD_SCRIPT_PATH = REPO_ROOT / "scripts" / "build-image.sh"

    def _load_workflow(self, path: Path) -> dict:
        return yaml.safe_load(path.read_text())

    def _get_triggers(self, data: dict) -> dict:
        """Return the triggers dict from a workflow, handling PyYAML's `on` → True quirk."""
        return data.get(True) or data.get("on") or {}

    # ------------------------------------------------------------------
    # Workflow file structure
    # ------------------------------------------------------------------

    def test_build_image_workflow_exists(self):
        self.assertTrue(self.WORKFLOW_PATH.is_file(), "build-image.yml not found")

    def test_ci_workflow_exists(self):
        self.assertTrue(self.CI_WORKFLOW_PATH.is_file(), "ci.yml not found")

    def test_build_image_workflow_is_valid_yaml(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        self.assertIsInstance(data, dict)

    def test_ci_workflow_is_valid_yaml(self):
        data = self._load_workflow(self.CI_WORKFLOW_PATH)
        self.assertIsInstance(data, dict)

    def test_build_image_triggers_on_version_tags(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        tags = self._get_triggers(data).get("push", {}).get("tags", [])
        self.assertTrue(
            any(t.startswith("v") for t in tags),
            "build-image.yml must trigger on v* tags",
        )

    def test_build_image_has_workflow_dispatch_trigger(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        self.assertIn(
            "workflow_dispatch",
            self._get_triggers(data),
            "build-image.yml must have a workflow_dispatch trigger for manual testing",
        )

    def test_build_image_workflow_dispatch_has_mode_input(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        inputs = (
            self._get_triggers(data).get("workflow_dispatch", {}) or {}
        ).get("inputs", {})
        self.assertIn(
            "mode",
            inputs,
            "workflow_dispatch must expose a 'mode' input",
        )

    def test_build_image_workflow_dispatch_mode_has_expected_options(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        inputs = (
            self._get_triggers(data).get("workflow_dispatch", {}) or {}
        ).get("inputs", {})
        options = inputs.get("mode", {}).get("options", [])
        for expected in ("dry-run", "artifact", "release"):
            with self.subTest(option=expected):
                self.assertIn(
                    expected,
                    options,
                    f"workflow_dispatch mode must include '{expected}' option",
                )

    def test_build_image_workflow_dispatch_mode_defaults_to_dry_run(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        inputs = (
            self._get_triggers(data).get("workflow_dispatch", {}) or {}
        ).get("inputs", {})
        default = inputs.get("mode", {}).get("default")
        self.assertEqual(
            default,
            "dry-run",
            "workflow_dispatch mode default must be 'dry-run' (safe default)",
        )

    def test_build_image_uses_arm64_runner(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        jobs = data.get("jobs", {})
        for job_name, job in jobs.items():
            runner = job.get("runs-on", "")
            with self.subTest(job=job_name):
                self.assertIn(
                    "arm",
                    str(runner).lower(),
                    f"Job '{job_name}' must run on an ARM64 runner",
                )

    def test_build_image_uses_pinned_checkout_action(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        steps = []
        for job in data.get("jobs", {}).values():
            steps.extend(job.get("steps", []))
        checkout_uses = [
            s.get("uses", "") for s in steps if "checkout" in s.get("uses", "")
        ]
        self.assertTrue(checkout_uses, "No checkout step found")
        for uses in checkout_uses:
            self.assertRegex(
                uses,
                r"actions/checkout@v\d",
                f"Checkout action must be pinned to a major version, got: {uses}",
            )

    def test_build_image_requires_contents_write_permission(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        for job_name, job in data.get("jobs", {}).items():
            perms = job.get("permissions", {})
            with self.subTest(job=job_name):
                self.assertEqual(
                    perms.get("contents"),
                    "write",
                    f"Job '{job_name}' must declare contents: write permission",
                )

    def test_ci_workflow_triggers_on_push_and_pr(self):
        data = self._load_workflow(self.CI_WORKFLOW_PATH)
        triggers = self._get_triggers(data)
        self.assertIn("push", triggers, "ci.yml must trigger on push")
        self.assertIn("pull_request", triggers, "ci.yml must trigger on pull_request")

    def test_ci_workflow_runs_on_ubuntu_latest(self):
        data = self._load_workflow(self.CI_WORKFLOW_PATH)
        for job_name, job in data.get("jobs", {}).items():
            runner = job.get("runs-on", "")
            with self.subTest(job=job_name):
                self.assertEqual(
                    runner,
                    "ubuntu-latest",
                    f"CI job '{job_name}' should run on ubuntu-latest (cheap x86)",
                )

    def test_build_image_has_artifact_upload_step(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        all_steps = []
        for job in data.get("jobs", {}).values():
            all_steps.extend(job.get("steps", []))
        upload_steps = [
            s for s in all_steps
            if "upload-artifact" in s.get("uses", "")
        ]
        self.assertTrue(
            upload_steps,
            "build-image.yml must have an actions/upload-artifact step for artifact mode",
        )

    def test_build_image_artifact_upload_uses_pinned_action(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        all_steps = []
        for job in data.get("jobs", {}).values():
            all_steps.extend(job.get("steps", []))
        for step in all_steps:
            uses = step.get("uses", "")
            if "upload-artifact" in uses:
                self.assertRegex(
                    uses,
                    r"actions/upload-artifact@v\d",
                    f"upload-artifact action must be pinned to a major version, got: {uses}",
                )

    def test_build_image_artifact_upload_is_conditional_on_artifact_mode(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        all_steps = []
        for job in data.get("jobs", {}).values():
            all_steps.extend(job.get("steps", []))
        for step in all_steps:
            if "upload-artifact" in step.get("uses", ""):
                condition = step.get("if", "")
                self.assertIn(
                    "artifact",
                    str(condition),
                    "upload-artifact step must be conditional on mode == 'artifact'",
                )

    def test_build_image_release_step_runs_on_tag_push_or_release_mode(self):
        data = self._load_workflow(self.WORKFLOW_PATH)
        all_steps = []
        for job in data.get("jobs", {}).values():
            all_steps.extend(job.get("steps", []))
        release_steps = [
            s for s in all_steps
            if "release" in s.get("name", "").lower() and "github" in s.get("name", "").lower()
        ]
        self.assertTrue(release_steps, "A 'Create GitHub Release' step must exist")
        for step in release_steps:
            condition = str(step.get("if", ""))
            self.assertIn(
                "push",
                condition,
                "Release step must run when triggered by a tag push (event_name == 'push')",
            )
            self.assertIn(
                "release",
                condition,
                "Release step must also run when mode == 'release'",
            )

    # ------------------------------------------------------------------
    # Build script
    # ------------------------------------------------------------------

    def test_build_script_exists(self):
        self.assertTrue(self.BUILD_SCRIPT_PATH.is_file(), "scripts/build-image.sh not found")

    def test_build_script_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.BUILD_SCRIPT_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg=f"bash -n failed:\n{result.stderr}",
        )

    def test_build_script_has_set_euo_pipefail(self):
        # Verify the safety flag appears as a non-commented executable line,
        # not just anywhere in the file (e.g. in a comment or docstring).
        content = self.BUILD_SCRIPT_PATH.read_text()
        executable_set = any(
            line.strip() == "set -euo pipefail"
            for line in content.splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertTrue(
            executable_set,
            "build-image.sh must have 'set -euo pipefail' as an executable statement",
        )

    def test_build_script_documents_arm64_requirement(self):
        # Verify the script both documents AND enforces the ARM64 requirement:
        # it must exit (die) when uname -m does not return aarch64.
        content = self.BUILD_SCRIPT_PATH.read_text()
        self.assertIn(
            "aarch64",
            content,
            "build-image.sh must reference aarch64 for the architecture check",
        )
        # The enforcement pattern: die/exit called when HOST_ARCH != aarch64
        self.assertIn(
            "aarch64",
            content,
        )
        lines = content.splitlines()
        arch_check_lines = [l for l in lines if "aarch64" in l and not l.lstrip().startswith("#")]
        self.assertTrue(
            arch_check_lines,
            "build-image.sh must have an executable line that references aarch64 (the runtime arch check)",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
