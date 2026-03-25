"""
generate-configs.py — Hearth Jinja2 template renderer (developer preview tool)

Renders every *.j2 template found across ansible/roles/*/templates/ into
system/generated/, preserving the base filename (e.g. nginx.conf.j2 →
system/generated/nginx.conf). Each role's defaults/main.yml is merged into
the template context so Ansible-specific variables (like deployment paths)
resolve correctly.

This script is NOT used during actual provisioning — Ansible's own template
module renders files directly onto the target host at provision time. This
exists purely so developers can inspect the rendered output locally without
spinning up a VM or running a full playbook.

Usage:
    python scripts/generate-configs.py [--config path/to/hearth.yaml]

Running the script twice (idempotent): files are only written when their
content changes.
"""

import argparse
import glob
import os
import sys

import yaml

# Allow "python scripts/generate-configs.py" from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from config import load_config, ConfigError

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError
except ImportError:
    print(
        "ERROR: jinja2 is not installed. Run: pip install jinja2",
        file=sys.stderr,
    )
    sys.exit(1)


# Collect templates from all Ansible role template directories
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
_ROLES_DIR = os.path.join(_REPO_ROOT, "ansible", "roles")
OUTPUT_DIR = os.path.join(_REPO_ROOT, "system", "generated")


def _find_template_dirs() -> list[str]:
    """Return all ansible/roles/*/templates/ directories that exist."""
    pattern = os.path.join(os.path.abspath(_ROLES_DIR), "*", "templates")
    return sorted(d for d in glob.glob(pattern) if os.path.isdir(d))


def _load_role_defaults(templates_dir: str) -> dict:
    """Load defaults/main.yml for the role that owns *templates_dir*."""
    role_dir = os.path.dirname(templates_dir)
    defaults_path = os.path.join(role_dir, "defaults", "main.yml")
    if os.path.isfile(defaults_path):
        with open(defaults_path, "r") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    return {}


def render_templates(config: dict, templates_dir: str, output_dir: str) -> list[str]:
    """Render all *.j2 templates from *templates_dir* into *output_dir*.

    Unknown template variables raise a :class:`jinja2.UndefinedError` (via
    ``StrictUndefined``) rather than silently expanding to an empty string.

    Returns a list of output file paths that were written (new or changed).
    """
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    os.makedirs(output_dir, exist_ok=True)

    written = []
    templates = sorted(
        t for t in env.list_templates() if t.endswith(".j2")
    )

    if not templates:
        print(f"No *.j2 templates found in '{templates_dir}'.")
        return written

    for template_name in templates:
        output_name = template_name[:-3]  # strip .j2
        output_path = os.path.join(output_dir, output_name)

        try:
            tmpl = env.get_template(template_name)
            rendered = tmpl.render(**config)
        except TemplateError as exc:
            print(
                f"ERROR rendering '{template_name}': {exc}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Only write if content changed (idempotent)
        existing = None
        if os.path.exists(output_path):
            with open(output_path, "r") as fh:
                existing = fh.read()

        if rendered != existing:
            with open(output_path, "w") as fh:
                fh.write(rendered)
            written.append(output_path)
            print(f"  Written:   {output_path}")
        else:
            print(f"  Unchanged: {output_path}")

    return written


def main():
    parser = argparse.ArgumentParser(
        description="Render Jinja2 templates from hearth.yaml"
    )
    parser.add_argument(
        "--config",
        default="hearth.yaml",
        metavar="PATH",
        help="Path to hearth.yaml (default: hearth.yaml)",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except (ConfigError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.abspath(OUTPUT_DIR)
    template_dirs = _find_template_dirs()

    print(f"Output : {output_dir}")
    print(f"Roles  : {len(template_dirs)} with templates")
    print()

    if not template_dirs:
        print("No ansible/roles/*/templates/ directories found.")
        return

    for tdir in template_dirs:
        role_name = os.path.basename(os.path.dirname(tdir))
        role_defaults = _load_role_defaults(tdir)
        context = {**role_defaults, **config}
        print(f"[{role_name}]")
        render_templates(context, tdir, output_dir)
        print()


if __name__ == "__main__":
    main()
