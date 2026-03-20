# Stage 0 — Base Infrastructure Tasks

These tasks establish the foundational repository structure, configuration system,
networking stack, and image-build pipeline for CafeBox.

Complete tasks in the order they are numbered. Each task is scoped to approximately
one hour of work for an intermediate software engineer.

---

## Task 0.01 — Repository Scaffolding ✅

Create all top-level directories and placeholder files described in the repository
structure diagram in `PLAN.md`. This gives every subsequent task a concrete place
to land.

**Deliverables:**
- Empty `cafe.yaml` (with `# TODO` comment)
- Empty `Makefile`
- Directories: `scripts/`

**Note:** `admin/`, `image/`, `portal/`, `services/`, `storage/`, `system/templates/`,
and `system/generated/` were initially scaffolded here but have since been removed —
all Jinja2 templates and their rendered output live inside the
`ansible/roles/<role>/templates/` directory structure instead.

**Acceptance criteria:** `tree -L 3` matches the layout in `PLAN.md`.

**Status: Complete**

---

## Task 0.02 — `cafe.yaml` Sample Configuration ✅

Write a fully-commented sample `cafe.yaml` that covers every field referenced in
the plan: box identity (`box.domain`, `box.name`), WiFi hotspot settings, storage
paths, and per-service enable flags.

**Deliverables:**
- `cafe.yaml` with realistic defaults and inline comments

**Acceptance criteria:**
- All keys referenced elsewhere in the codebase load without KeyError.
- File is valid YAML (`python -c "import yaml; yaml.safe_load(open('cafe.yaml'))"`).

**Status: Complete**

---

## Task 0.03 — `scripts/config.py` — Configuration Loader ✅

Write a small Python module that loads and validates `cafe.yaml`. It must be
importable by both `install.sh` (via `python scripts/config.py`) and the admin
backend.

**Deliverables:**
- `scripts/config.py` exposing a `load_config(path="cafe.yaml")` function that
  returns a validated dict/namespace.
- Basic sanity checks (required keys present, domain is a valid hostname, etc.).

**Acceptance criteria:**
- `python scripts/config.py` prints resolved config without errors.
- Missing required key raises a clear `ConfigError` with the key name.

**Status: Complete**

---

## Task 0.04 — `scripts/generate-configs.py` — Jinja2 Template Renderer ✅

Write the script that reads `cafe.yaml` (via `config.py`) and renders every
Jinja2 template found across `ansible/roles/*/templates/` into `system/generated/`
(grouped by role). Ansible's own `template` module renders templates directly onto
the target host at provision time; `generate-configs.py` serves as a local
developer tool for inspecting the rendered output without running a full playbook.

**Deliverables:**
- `scripts/generate-configs.py`
- At least one stub template (`ansible/roles/nginx/templates/nginx.conf.j2`) and its
  expected rendered form documented in comments.

**Acceptance criteria:**
- Running `python scripts/generate-configs.py` produces files in `system/generated/`.
- Re-running is idempotent.
- Unknown template variables raise a clear error, not a silent empty string.

**Status: Complete**

---

## Task 0.05 — `Makefile` Dev Shortcuts ✅

Add the developer convenience targets described in `PLAN.md`:
`vm-start`, `vm-stop`, `vm-ssh`, `vm-destroy`, `logs`.

`install` and `generate-configs` are intentionally **not** exposed as Makefile
targets. Both are invoked automatically by `vagrant provision` (via the
Vagrantfile shell provisioner), so there is no need for a developer to call them
directly. Exposing them as top-level targets would create a parallel, out-of-band
code path that could diverge from the provisioning workflow.

**Deliverables:**
- `Makefile` with each target delegating directly to `vagrant`.
- `.PHONY` declaration for all targets.

**Acceptance criteria:**
- `make help` (or `make` with a default help target) lists all targets with
  one-line descriptions.
- Each target fails with a descriptive message if vagrant is not installed.
- `make vm-start` exits non-zero with a message mentioning "vagrant" when vagrant
  is not installed.

**Status: Complete**

---

## Task 0.06 — `Vagrantfile` — Dev VM Definition ✅

Define the development VM using **Vagrant** so every contributor can spin up an
identical environment with a single command. Vagrant replaces the QEMU/libvirt
`scripts/vm.sh` approach: the `Vagrantfile` at the repo root is the single
source of truth for the dev environment.

**Box choice:** `debian/trixie64` — a Debian base compatible with Raspberry Pi OS
Lite 64-bit, ensuring parity between dev and production.

**Provisioner:** Vagrant's built-in **Ansible provisioner** runs `ansible/site.yml`
against the VM over SSH — the same playbook used to provision real Pi hardware
directly, and to build flashable SD card images.

**Deliverables:**
- `Vagrantfile` at the repository root with:
  - `config.vm.box = "debian/trixie64"`, hostname `cafebox-dev`
  - Forwarded ports: guest 80 → host 8080 (portal), guest 8000 → host 8000
    (admin backend), both bound to `127.0.0.1`
  - Synced folder: repo root → `/vagrant` inside the VM
  - VirtualBox provider: 1 GB RAM, 2 CPUs, name `cafebox-dev`
  - Ansible provisioner: `ansible.playbook = "ansible/site.yml"`
- `ansible/` directory with best-practice layout (see Task 0.06a below)
- Updated `Makefile` `vm-*` targets that delegate to `vagrant` commands:
  - `vm-start` → `vagrant up`
  - `vm-stop` → `vagrant halt`
  - `vm-ssh` → `vagrant ssh`
  - `vm-destroy` → `vagrant destroy -f`
  - `logs` → `vagrant ssh -c "journalctl -f -u 'cafebox-*'"`
  - Each target checks `command -v vagrant` and exits with a descriptive
    error message if vagrant is not installed.

**Acceptance criteria:**
- `vagrant validate` passes against the `Vagrantfile` (requires vagrant installed).
- `make vm-start` exits non-zero with a message mentioning "vagrant" when vagrant
  is not installed.
- `make help` lists `vm-destroy` as a target.
- `scripts/vm.sh` is **not** created; vagrant is the only VM management layer.

**Status: Complete**

---

## Task 0.06a — `ansible/` — Ansible Provisioner Directory Structure ✅

Initialise the Ansible directory layout following
[Ansible best practices](https://docs.ansible.com/ansible/latest/tips_tricks/ansible_tips_tricks.html).
Each CafeBox service gets its own role so concerns are cleanly separated and
roles can be enabled/disabled independently via `cafe.yaml`.

**Deliverables:**
- `ansible/ansible.cfg` — project-scoped Ansible config (roles path, inventory
  defaults, SSH settings)
- `ansible/site.yml` — top-level playbook that applies all roles to the
  `cafebox` host group
- `ansible/inventory/development` — static inventory for the Vagrant dev VM
- `ansible/inventory/production` — stub inventory for real Pi targets
- `ansible/group_vars/all.yml` — variables shared across all hosts (loaded
  from `cafe.yaml` values)
- `ansible/roles/<name>/` for each service, each containing:
  - `tasks/main.yml`
  - `handlers/main.yml`
  - `defaults/main.yml`
  - `meta/main.yml`

  Roles:
  | Role | Responsibility |
  |------|---------------|
  | `common` | Base packages, system users, directory layout |
  | `nginx` | Web server, portal reverse-proxy |
  | `conduit` | Matrix homeserver |
  | `element_web` | Matrix web client |
  | `calibre_web` | eBook library |
  | `kiwix` | Offline Wikipedia / ZIM reader |
  | `navidrome` | Music streaming server |
  | `admin` | Admin backend + frontend |
  | `wifi` | hostapd + dnsmasq hotspot |
  | `firewall` | nftables rules |

**Acceptance criteria:**
- `ansible-lint ansible/site.yml` reports no errors (requires ansible-lint).
- `ansible-playbook --syntax-check -i ansible/inventory/development ansible/site.yml`
  passes.
- Each role directory contains at minimum `tasks/main.yml`.

**Status: Complete**

---

## Task 0.07 — `scripts/dev-hosts.sh` — Local DNS Entries ✅

Write a script that adds (and can remove) `*.cafe.box` wildcard entries to
`/etc/hosts` so the developer's browser resolves the box domain locally.

**Deliverables:**
- `scripts/dev-hosts.sh add` — appends entries, idempotent.
- `scripts/dev-hosts.sh remove` — removes the entries.

**Acceptance criteria:**
- Running `add` twice does not duplicate entries.
- Script requires `sudo` and exits with a helpful message if not run as root.

**Status: Complete**

---

## Task 0.08 — `ansible/roles/common` Bootstrap Tasks ✅

Implement the `common` Ansible role to bootstrap the box: install system packages,
create the `cafebox` system user, set up the `/srv/cafebox` directory layout, call
`scripts/generate-configs.py`, and enable systemd units.

**Deliverables:**
- `ansible/roles/common/tasks/main.yml` with clearly separated phases: package
  installation, user/directory setup, config generation, service enablement.
- Role detects whether it is running on Pi hardware vs. VM and logs accordingly.

**Acceptance criteria:**
- `ansible-playbook --syntax-check -i ansible/inventory/development ansible/site.yml` passes.
- Role is idempotent: running it twice does not break a working installation.
- Each phase uses `block/rescue` or `failed_when` so a failure stops the play immediately.

**Status: Complete**

## Task 0.09 — Network Policy: Firewall Rules (Hotspot-Only, Default-Deny) ✅

Implement the threat-model firewall rules from Stage 0.0 of `PLAN.md` using
`nftables` (preferred) or `iptables`.

Rules must enforce:
- No WAN routing/NAT for connected clients.
- Allow DHCP (UDP 67/68), DNS (UDP/TCP 53), and HTTP (TCP 80) on the AP
  interface only.
- Drop everything else from clients.
- Allow full outbound from the box itself for build-time downloads.

**Deliverables:**
- `ansible/roles/firewall/templates/nftables.conf.j2` (or `iptables.rules.j2`)
- `ansible/roles/firewall/tasks/main.yml` that deploys the rendered rules and
  ensures they persist across reboots.

**Acceptance criteria:**
- Rules template renders without Jinja2 errors.
- Comments in the file map each rule to the threat-model bullet it addresses.

**Status: Complete**

---

## Task 0.10 — `hostapd` + `dnsmasq` Configuration Templates ✅

Create Jinja2 templates for `hostapd.conf` and `dnsmasq.conf` so the WiFi
hotspot and captive-portal DNS are driven by `cafe.yaml`.

`dnsmasq` must:
- Resolve `*.cafe.box` to the box IP.
- Serve DHCP leases on the AP interface.
- Return the box IP for all other DNS queries (captive portal intercept).

**Deliverables:**
- `ansible/roles/wifi/templates/hostapd.conf.j2`
- `ansible/roles/wifi/templates/dnsmasq.conf.j2`
- `ansible/roles/wifi/tasks/main.yml` that installs `hostapd` and `dnsmasq`,
  deploys the rendered configs, and enables/starts both services.
- `ansible/roles/wifi/handlers/main.yml` with restart handlers for both services.
- `ansible/roles/wifi/defaults/main.yml` with sensible defaults.

**Acceptance criteria:**
- Both templates render with the sample `cafe.yaml` without errors.
- Rendered `dnsmasq.conf` contains a `address=/#/<box_ip>` line.

**Status: Complete**

---

## Task 0.11 — nginx Configuration Template + Captive Portal Redirect ✅

Create a Jinja2 template for the main `nginx.conf` that:
- Serves the landing portal on port 80.
- Includes the captive-portal redirect: `location /generate_204 { return 302 http://{{ box.domain }}/; }`.
- Includes stub `location` blocks for each service (commented-out until the
  service is installed).

**Deliverables:**
- `ansible/roles/nginx/templates/nginx.conf.j2`

**Acceptance criteria:**
- Template renders to valid nginx configuration (`nginx -t` passes against the
  rendered file).
- `/generate_204` block is present and points to `box.domain`.

**Status: Complete**

---

## Task 0.12 — Portal Landing Page (`ansible/roles/nginx`)✅

Build the portal landing page. It must:
- Follow the UX and visual direction in [`STYLEGUIDE.md`](../STYLEGUIDE.md).
- Call `GET /api/public/services/status` on page load.
- Render a tile grid from the response (name, enabled, URL).
- Show the first-boot password banner if the API response includes
  `first_boot: true`.
- Work with no JavaScript frameworks (vanilla JS acceptable; no CDN fetches).

**Deliverables:**
- Portal `index.html` managed by the `nginx` role (e.g. as a file in
  `ansible/roles/nginx/files/index.html` or a template in `templates/`)
- Portal UX reference documented in [`STYLEGUIDE.md`](../STYLEGUIDE.md)

**Acceptance criteria:**
- Page renders correctly with a hard-coded mock API response (no server needed).
- Password banner is visible when mock response has `first_boot: true`.
- Password banner is hidden when `first_boot: false`.
- No external CDN resources referenced.

**Status: Complete**

---

## Task 0.13 — First-Boot Credential Generation (`ansible/roles/common`) ✅

Implement the one-shot first-boot credential generator:
- Generate a random 12-character alphanumeric admin password.
- Hash it and set it for the `cafebox-admin` system user.
- Write a flag file (e.g., `/var/lib/cafebox/first-boot-done`) so the script
  does not re-run.
- Store the plaintext password temporarily in a readable location so the portal
  can display it (e.g., `/run/cafebox/initial-password`).

**Deliverables:**
- `ansible/roles/common/files/first-boot.sh` (deployed to the target by the role)
- `ansible/roles/common/files/first-boot.service` (systemd oneshot, `Before=nginx.service`)
- Task in `ansible/roles/common/tasks/main.yml` that installs and enables the unit.

**Acceptance criteria:**
- Script is idempotent: second run exits 0 and does nothing.
- Password file has permissions `0400` owned by `cafebox-admin` (the admin
  backend process user from Task 1.05), so the API endpoint in Task 1.06 can
  read it. The portal landing page reads the flag via the
  `/api/public/services/status` API — not by accessing the file directly —
  so nginx's process user does not need read access to this file.
- `bash -n` passes on the deployed script.

**Status: Complete**

---

## Task 0.14 — Storage Layout (`ansible/roles/common`)

Finalise the storage directory layout so each service's writable data lives under
a single top-level mount point, making it easy to back up or migrate to external
media.

Service paths are declared in `cafe.yaml` (`storage.locations.*`) and mirrored in
`ansible/group_vars/all.yml`. The `common` role creates them as plain directories
via the `cafebox_storage_dirs` loop already present in Phase 2. No symlinks are
used: all service config templates reference `{{ storage.locations.<service> }}`
rather than hard-coded system paths, so the entire data tree can be relocated by
updating `storage.base` in `cafe.yaml` and re-provisioning.

**Deliverables:**

1. **Sync `cafebox_storage_dirs`** in `ansible/roles/common/defaults/main.yml` with
   `storage.locations.*` in `ansible/group_vars/all.yml` and `cafe.yaml`. Every
   service directory defined in `cafe.yaml` must appear in this list so a fresh
   provision always produces a complete layout.

2. **Per-service ownership.** The `common` role creates all service directories
   owned by the `cafebox` system user. Any service role that runs under a different
   dedicated user must `chown` its own storage subdirectory in its own role's
   tasks — not in `common`.

3. **Document the external-storage migration path** in `cafe.yaml`. Add a comment
   block to the `storage:` section explaining the supported workflow for moving data
   to a USB drive:
   - Mount the drive at `storage.base` (e.g. `/srv/cafebox`) before provisioning, OR
   - Update `storage.base` to the new mount point (e.g. `/mnt/cafebox-data`) and
     re-run `ansible-playbook`. All directories are recreated and service configs
     are re-rendered automatically.

**Acceptance criteria:**
- `cafebox_storage_dirs` in `defaults/main.yml` matches the keys in
  `storage.locations` in `group_vars/all.yml` and `cafe.yaml`.
- Role is idempotent: running the playbook twice makes no changes on the second run.
- `ansible-playbook --syntax-check -i ansible/inventory/development ansible/site.yml`
  passes.
- `cafe.yaml` storage section includes a comment explaining the external-media
  migration workflow.

---

## Task 0.15 — Flashable Image Builder (`scripts/build-image.sh`)

Write the script that produces a flashable `.img.xz` Raspberry Pi image by
running the Ansible playbook against a loop-mounted disk image (or via pi-gen):
1. Start from a Raspberry Pi OS Lite base.
2. Run `ansible/site.yml` against the image (chroot or direct provisioning).
3. Compress the result to `.img.xz`.

**Deliverables:**
- `scripts/build-image.sh`
- `image/README.md` with instructions for building and flashing

**Acceptance criteria:**
- `bash -n scripts/build-image.sh` passes.
- README documents required host tools and estimated build time.

---

## Task 0.16 — `.github/workflows/build-image.yml` CI Image Build

Create a GitHub Actions workflow that:
- Triggers on tag push (`v*`).
- Runs `scripts/build-image.sh`.
- Uploads the resulting `.img.xz` as a release asset.

**Deliverables:**
- `.github/workflows/build-image.yml`

**Acceptance criteria:**
- Workflow YAML is valid (`actionlint` or `yamllint`).
- Uses pinned action versions (e.g., `actions/checkout@v4`).
- Workflow only runs on version tags, not on every push.
