# Stage 3 — Kiwix Offline Wikipedia Tasks

These tasks implement the Kiwix offline content reader, serving a full offline
copy of Wikipedia (and optionally other ZIM content) at `/wiki/`. Content is
served directly from the box with no internet connection required.

Complete tasks in the order they are numbered. Each task is scoped to
approximately one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 0 and Stage 1 tasks must be complete before
starting Stage 3.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│ nginx                                           │
│  /wiki     → 301 /wiki/                        │
│  /wiki/    → proxy to kiwix-serve:8888         │
└────────────────────┬────────────────────────────┘
                     │ HTTP reverse proxy
┌────────────────────▼────────────────────────────┐
│ kiwix.service  (kiwix-serve)                    │
│  • Serves ZIM files from /srv/cafebox/kiwix/    │
│  • Handles search, article rendering            │
│  • Exposes HTTP on 127.0.0.1:8888              │
└────────────────────┬────────────────────────────┘
                     │ ZIM files
┌────────────────────▼────────────────────────────┐
│ /srv/cafebox/kiwix/                             │
│  wikipedia_en_all_mini_*.zim   (≈ 1 GB)        │
│  or wikipedia_en_all_maxi_*.zim (≈ 90 GB)      │
│  (operator uploads via admin UI or scp)         │
└─────────────────────────────────────────────────┘
```

**Design decisions:**
- **kiwix-serve** is the official Kiwix server daemon — a single binary with no
  runtime dependencies beyond the ZIM files.
- **Storage planning is the operator's responsibility.** The mini Wikipedia ZIM
  is ≈ 1 GB (text only). The maxi ZIM with images is ≈ 90 GB — larger than a
  typical SD card. Operators deploying the full Wikipedia must provide external
  storage (USB SSD) mounted at or under `/srv/cafebox/`.
- **ZIM uploads** use the existing admin upload endpoint from Task 1.11; the
  `kiwix` storage location is already declared in `cafe.yaml`.
- **No content is bundled** with the Ansible role. The role installs kiwix-serve
  and configures the service; ZIM files are added by the operator post-provision.
- **Graceful no-content state:** if no ZIM files are present, kiwix-serve still
  starts and returns an empty library page rather than failing.

---

## Storage Reference

| ZIM package | Size | Contents |
|---|---|---|
| `wikipedia_en_all_mini` | ≈ 1 GB | All articles, text only |
| `wikipedia_en_all_maxi` | ≈ 90 GB | All articles, text + images |
| `wikipedia_en_top_mini` | ≈ 200 MB | Top ~100 k articles, text only |

ZIM files are distributed by the Kiwix project at `download.kiwix.org`. The
operator must download them separately and upload via the admin UI or `scp`.

---

## Task 3.01 — kiwix-serve Installation

Install the kiwix-serve binary and create the `kiwix` system user that runs
the service.

**kiwix-serve** is available as a static binary for ARM (armhf / arm64)
from the Kiwix GitHub releases. It is not in the Debian package repositories
for all architectures, so the role should download the appropriate release
binary for the detected platform.

**Deliverables:**
- `ansible/roles/kiwix/tasks/main.yml` — implement the placeholder:
  - Create `kiwix` system user and group.
  - Detect architecture (`ansible_architecture`) and download the correct
    kiwix-serve binary from the Kiwix GitHub releases to `/usr/local/bin/kiwix-serve`.
  - Set `mode: "0755"` on the binary.
  - Ensure `/srv/cafebox/kiwix/` exists and is owned by `kiwix:kiwix`.
- `ansible/roles/kiwix/vars/main.yml` — pin the kiwix-serve version.

**Acceptance criteria:**
- `/usr/local/bin/kiwix-serve --version` succeeds on both `armv7l` (Pi) and
  `x86_64` (Vagrant VM) architectures.
- Binary is owned by `root` and executable by all.
- `/srv/cafebox/kiwix/` exists and is writable by the `kiwix` user.
- Tests pass: binary exists; storage directory exists.

---

## Task 3.02 — kiwix.service Systemd Unit

Create and enable the systemd service that runs kiwix-serve.

**Deliverables:**
- `ansible/roles/kiwix/files/kiwix.service`:
  ```ini
  [Unit]
  Description=Kiwix Offline Content Server
  After=network.target

  [Service]
  Type=simple
  User=kiwix
  Group=kiwix
  ExecStart=/usr/local/bin/kiwix-serve \
      --library \
      --port=8888 \
      --address=127.0.0.1 \
      /srv/cafebox/kiwix/
  Restart=on-failure
  RestartSec=5
  PrivateTmp=true
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=true
  ReadWritePaths=/srv/cafebox/kiwix

  [Install]
  WantedBy=multi-user.target
  ```
- Tasks in `main.yml` deploy and enable the service.

**Acceptance criteria:**
- `kiwix.service` reaches `active (running)` after provision.
- Service responds to `curl http://127.0.0.1:8888/` with a valid HTTP response.
- With no ZIM files present, kiwix-serve still starts and returns a library
  page (even if empty).
- Tests pass: service unit exists; contains `PrivateTmp=true` and
  `NoNewPrivileges=true`; tasks enable `kiwix.service`.

---

## Task 3.03 — nginx Routing

Update the nginx configuration template to reverse-proxy to kiwix-serve.

**Location blocks (conditional on `services.kiwix.enabled`):**
- `location = /wiki` → `return 301 /wiki/`
- `location /wiki/` → `proxy_pass http://127.0.0.1:8888`

kiwix-serve generates internal links relative to its own root. The nginx
`location /wiki/` block must forward the path correctly so article links
work without rewriting. Test with and without trailing slash.

**Deliverables:**
- Updated `ansible/roles/nginx/templates/nginx.conf.j2`.

**Acceptance criteria:**
- `curl -I http://cafe.box/wiki` returns 301 to `/wiki/`.
- `curl http://cafe.box/wiki/` returns a valid HTML response from kiwix-serve.
- Blocks are absent when `services.kiwix.enabled: false`.
- Tests pass: rendered config contains `= /wiki` redirect and `/wiki/` proxy
  block when enabled; both are absent when disabled.

---

## Task 3.04 — ZIM Management: Scan and Reload

kiwix-serve discovers ZIM files at startup. Provide an admin mechanism to
trigger a rescan after the operator uploads a new ZIM file without requiring
a manual service restart.

**Deliverables:**
- `POST /api/admin/services/kiwix/rescan` backend endpoint:
  - Requires session + CSRF token.
  - Runs `sudo systemctl restart kiwix.service` (already covered by the
    sudoers template — ensure `kiwix.service` is listed there).
  - Returns `{"status": "restarted"}` on success.
- Update `ansible/roles/admin/files/backend/services_map.py` to include
  the `kiwix` entry:
  ```python
  "kiwix": {
      "unit": "kiwix.service",
      "name": "Wikipedia",
      "url_path": "/wiki/",
  }
  ```
- Update `ansible/roles/admin/templates/sudoers-cafebox.j2` to include
  `kiwix.service` start/stop/restart entries.

**Acceptance criteria:**
- Adding a ZIM file to `/srv/cafebox/kiwix/` and calling the rescan endpoint
  causes the new content to appear in the kiwix library page.
- The service can be started/stopped via the standard admin API.
- Tests pass: sudoers template contains `kiwix.service` entries; `services_map.py`
  contains the kiwix entry.

---

## Task 3.05 — Portal Tile + cafe.yaml Integration

Wire Kiwix into the portal tile system and `cafe.yaml`.

**Deliverables:**
- `cafe.yaml` — `services.kiwix.enabled` is already present; verify it
  drives the nginx conditional and the public API tile.
- `ansible/roles/nginx/files/index.html` — ensure the Wikipedia tile links
  to `/wiki/` (currently the tile may link to a placeholder URL).
- Brief operator note added to `cafe.yaml` comments explaining storage
  requirements and where to find ZIM files.

**Acceptance criteria:**
- When `services.kiwix.enabled: true`, the portal tile appears and links
  to `/wiki/`.
- When `services.kiwix.enabled: false`, the tile is absent from the portal.
- `cafe.yaml` comments explain minimum storage requirements.
- Tests pass: public services API includes/excludes kiwix tile based on
  enabled flag; index.html links to `/wiki/` when enabled.
