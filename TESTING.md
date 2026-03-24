# TESTING

This document defines the testing strategy and quality guidelines for CafeBox.

## Goals

- Keep feedback loops fast during development.
- Preserve loose coupling between roles.
- Keep deployable role payloads clean and portable.
- Use full VM provisioning for integration confidence, not as the only test path.

## Testing Philosophy

Use a layered model:

1. **Static/structural checks first** (fastest)
2. **Targeted role-level tests second**
3. **Full Vagrant integration smoke last**

This gives quick diagnosis while still validating cross-role behavior.

## Environment Model (Single Root Virtualenv)

Use a single repository-root virtualenv for local development and tests.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install baseline test dependencies:

```bash
pip install pytest pyyaml jinja2
```

Install role-specific Python deps needed for local tests (currently admin backend):

```bash
pip install -r ansible/roles/admin/files/backend/requirements.txt
```

## Python Service Runtime Standard

CafeBox uses two different Python environment scopes for different purposes:

1. **Root `.venv` (repository root)** for local development and tests.
2. **Per-service runtime `.venv` (on target host)** for deployed Python services.

### Runtime policy

- Python-backed services should run from a dedicated service venv on the target host.
- Do not install service app dependencies into the OS Python directly with pip.
- Service systemd units should execute binaries from that service venv.
- Keep dependencies pinned/tightly version-bounded to reduce upgrade risk.

### Why this is the default

- Preserves dependency isolation between services.
- Avoids OS Python pollution and distro package conflicts.
- Improves role portability and predictable rollbacks.
- Keeps coupling low as more services are added.

### Resource guidance for constrained devices

- Venv directories primarily consume disk; they do not consume steady RAM when idle.
- RAM impact is dominated by running processes, not by venv existence.
- Keep runtime requirements lean and avoid unnecessary extras on low-resource targets.
- If multiple internal Python services are later added and have compatible dependencies,
  a shared runtime venv may be considered as an explicit optimization tradeoff.

## Artifact Hygiene (Critical)

Role payload directories must contain **deployable artifacts only**.

Do **not** keep local runtime artifacts in `ansible/roles/*/files/`, including:

- `.venv/`
- `__pycache__/`
- generated runtime caches/logs
- editor temp files

Why this matters:

- Ansible `copy` recurses whatever is present in role `files/` trees.
- `.gitignore` does **not** prevent Ansible from copying local artifacts.
- Payload contamination can cause slow or hanging provisioning (especially on Vagrant synced folders).

## Test Layers

### Layer 1 — Static and Structural (Required)

Run quick checks that do not require provisioning:

```bash
python -m pytest tests/test_base_infrastructure.py -v
```

This validates repository structure, YAML/template parseability, workflows, and role wiring.

### Layer 2 — Role-Level Local Tests (Required where applicable)

For Python-backed roles (e.g., admin backend), run targeted tests:

```bash
python -m pytest tests/test_admin_backend.py -v
```

Other role-focused tests can also be run individually:

```bash
python -m pytest tests/test_task105_sudoers.py -v
python -m pytest tests/test_task112_nginx.py -v
```

### Layer 3 — Full Integration (Required for integration-sensitive changes)

Use Vagrant provisioning to validate cross-role behavior and runtime wiring:

```bash
vagrant up
vagrant ssh -c "journalctl -f -u 'cafebox-*'"
```

Use this for changes affecting:

- systemd service lifecycle
- nginx routing/proxying
- firewall/network behavior
- Ansible role interactions across the full stack

## Role Testability Contract

Each role should be testable independently at least at one of these levels:

- **Static/config level**: templates, tasks wiring, defaults, file structure
- **Local runtime level** (if app-backed): targeted unit/API tests
- **Integration level**: validated through VM provisioning when role interactions matter

Not every role needs its own runtime process, but every role must have a clear validation path.

## Recommended Local Workflows

### Fast local loop (while coding)

```bash
source .venv/bin/activate
python -m pytest tests/test_<relevant_file>.py -v
```

### Pre-PR loop

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

### Pre-merge / release-sensitive loop

```bash
vagrant up
vagrant provision   # optionally reprovision explicitly
vagrant ssh -c "journalctl -f -u 'cafebox-*'"
```

## CI Alignment

CI already follows a single-interpreter model and runs pytest plus syntax checks.

Local testing should mirror CI as closely as practical:

- same Python major version family
- same dependency sets
- same pytest entry points

Reference: `.github/workflows/ci.yml`.

## Definition of Done (Testing)

A change is testing-complete when:

1. Relevant targeted tests pass.
2. Full `tests/` passes for non-trivial changes.
3. Integration smoke is run when change affects provisioning/runtime wiring.
4. No local runtime artifacts are introduced into role payload trees.

## Troubleshooting

If provisioning appears to hang during an Ansible copy task:

1. Check for unexpected large/local artifacts under `ansible/roles/*/files/`.
2. Remove `.venv`, `__pycache__`, and generated files from payload trees.
3. Re-run targeted tests first, then reprovision.

If Vagrant output is noisy or slow to diagnose, isolate with targeted pytest first, then validate with full integration.

## Related Files

- `README.md`
- `.github/workflows/ci.yml`
- `tests/test_base_infrastructure.py`
- `tests/test_admin_backend.py`
- `ansible/roles/admin/tasks/main.yml`
- `ansible/roles/admin/README.md`
