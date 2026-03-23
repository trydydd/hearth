# Stage 2 — Matrix Chat (Conduit + Element Web) Tasks

These tasks integrate a self-hosted Matrix homeserver (Conduit) and the Element
Web client into CafeBox, enabling private group chat over the local hotspot with
no internet connection.

Complete tasks in the order they are numbered. Each task is scoped to approximately
one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 0 and Stage 1 tasks must be complete before starting Stage 2.

---

## Task 2.01 — E2EE / Ephemerality Policy Documentation

CafeBox does **not** guarantee that messages are erased when users disconnect.
Document this policy clearly so users are not misled.

**Deliverables:**
- `ansible/roles/conduit/files/PRIVACY.md` explaining:
  - Messages are stored on the box until the operator clears them.
  - E2EE is available between clients but the server stores ciphertext.
  - Users should assume messages persist for the session lifetime of the box.
- A one-sentence privacy notice to add to `ansible/roles/nginx/files/index.html` near the chat tile.

**Acceptance criteria:**
- `PRIVACY.md` is clear, non-technical language suitable for end users.
- Privacy notice is visible on the portal without clicking through.
- Tests are written and pass: `PRIVACY.md` exists and contains the required sections; the privacy notice string is present in `index.html`.

---

## Task 2.02 — Conduit Download in Build Script

Update `scripts/build-image.sh` to download a pinned release of Conduit (the Matrix
homeserver) and embed it in the image.

**Deliverables:**
- Variable `CONDUIT_VERSION` near the top of `scripts/build-image.sh` (e.g., `v0.9.0`).
- Download step that fetches the pre-built ARM binary from the Conduit GitHub
  releases and verifies its SHA-256 checksum.
- Binary installed to `/usr/local/bin/conduit` in the image.

**Acceptance criteria:**
- Build script fails loudly if the checksum does not match.
- Downloaded binary is not committed to the repository (`.gitignore` updated).
- `bash -n scripts/build-image.sh` still passes after the change.
- Tests are written and pass: `bash -n scripts/build-image.sh` succeeds and the build script contains checksum verification logic for the Conduit binary.

---

## Task 2.03 — Conduit Configuration Template

Create a Jinja2 template for the Conduit `conduit.toml` configuration file,
driven by `cafe.yaml`.

Required settings:
- `server_name` = `{{ box.domain }}`
- `database_path` = storage path from `cafe.yaml`
- `allow_registration = true` (open registration for hotspot users)
- `allow_federation = false` (offline-only)
- `max_request_size` = configurable, default `20_000_000`

**Deliverables:**
- `ansible/roles/conduit/templates/conduit.toml.j2`

**Acceptance criteria:**
- Template renders with sample `cafe.yaml` without errors.
- `allow_federation` is always `false` regardless of operator config (hardcoded
  for security).
- Rendered file is valid TOML (`python -c "import tomllib; tomllib.load(...)"` on
  Python 3.11+).
- Tests are written and pass: template renders to valid TOML with the sample `cafe.yaml`; `allow_federation` is `false` in the rendered output.

---

## Task 2.04 — Conduit systemd Service Unit

Create the systemd service unit that runs Conduit as a non-root system user.

**Deliverables:**
- `ansible/roles/conduit/templates/conduit.service.j2` (if any value is templated,
  otherwise `ansible/roles/conduit/files/conduit.service` as a static file)
- Service runs as `conduit` system user (created by the conduit role).
- `Restart=on-failure`, `PrivateTmp=true`, `NoNewPrivileges=true`.

**Acceptance criteria:**
- `systemd-analyze verify conduit.service` passes (or equivalent offline check).
- `ansible/roles/conduit/tasks/main.yml` creates the `conduit` user and enables the service.
- Tests are written and pass: service unit file exists and contains `Restart=on-failure`, `PrivateTmp=true`, and `NoNewPrivileges=true`.

---

## Task 2.05 — Element Web Download + Deployment in Build Script

Update `scripts/build-image.sh` to download a pinned Element Web release and include it
in the image.

**Deliverables:**
- Variable `ELEMENT_WEB_VERSION` near the top of `scripts/build-image.sh`.
- Download and extract the Element Web tarball from GitHub releases, verify SHA-256.
- Static files installed to `/srv/cafebox/element-web/` in the image.

**Acceptance criteria:**
- Build script fails if checksum does not match.
- Downloaded tarball is not committed to the repository.
- Installed directory contains `index.html` and `config.json`.
- Tests are written and pass: `bash -n scripts/build-image.sh` succeeds and the build script contains checksum verification logic for the Element Web tarball.

---

## Task 2.06 — Element Web `config.json` Template

Create the Element Web configuration so it points to the local Conduit homeserver.

**Deliverables:**
- `ansible/roles/element_web/templates/element-web-config.json.j2` with:
  - `"default_server_config"` → `m.homeserver.base_url` = `http://matrix.{{ box.domain }}`
  - `"brand"` = `{{ box.name }}`
  - `"disable_guests": false` (allow unregistered browsing)
  - `"roomDirectory": {"servers": ["{{ box.domain }}"]}` (local rooms only)

**Acceptance criteria:**
- Rendered `config.json` is valid JSON.
- `base_url` resolves to a URL reachable on the hotspot.
- No hardcoded domains in the template.
- Tests are written and pass: rendered `config.json` is valid JSON, `base_url` contains no hardcoded domains, and all required keys are present.

---

## Task 2.07 — nginx Reverse Proxy for Matrix + Element Web

Update the nginx configuration template to expose Matrix and Element Web:
- `/_matrix/` → Conduit (http://127.0.0.1:6167) — required by Matrix spec.
- `/_synapse/` → Conduit (for compatibility, if used).
- `/element/` → Element Web static files at `/srv/cafebox/element-web/`.
- Well-known delegation: `/.well-known/matrix/server` and `/.well-known/matrix/client`.

**Deliverables:**
- Updated `ansible/roles/nginx/templates/nginx.conf.j2`

**Acceptance criteria:**
- Rendered config passes `nginx -t`.
- `curl http://cafe.box/_matrix/client/versions` returns a JSON response via the
  `/_matrix/` location block (once Conduit is running). Note: `matrix.cafe.box`
  is not used as a virtual-host subdomain here; the `/_matrix/` path prefix is
  what the Matrix spec requires, served from the same `cafe.box` domain.
- `curl http://cafe.box/.well-known/matrix/server` returns
  `{"m.server": "cafe.box:80"}` (or the configured port).
- Tests are written and pass: rendered nginx config passes `nginx -t` and contains `/_matrix/` and `/.well-known/matrix/` location blocks.

---

## Task 2.08 — Chat Tile on Portal Landing Page

Add the Matrix Chat tile to the portal landing page service grid. The tile should
appear automatically when the `chat` service is enabled in `cafe.yaml`.

**Deliverables:**
- Ensure `/api/public/services/status` includes the chat service tile (update
  `ansible/roles/admin/files/backend/routers/public.py` service list if hardcoded).
- `ansible/roles/nginx/files/index.html` tile links to `http://element.cafe.box/` (or `/element/`).
- Tile shows "Chat" as the label and a chat bubble icon (inline SVG, no CDN).

**Acceptance criteria:**
- Portal renders the chat tile when `services.chat.enabled: true` in `cafe.yaml`.
- Portal omits the chat tile when `services.chat.enabled: false`.
- Link opens Element Web in the same tab.
- Tests are written and pass: `/api/public/services/status` includes the chat tile when `services.chat.enabled: true` and omits it when `services.chat.enabled: false`.
