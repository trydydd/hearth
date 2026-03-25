# Stage 4 — Music Library Tasks

These tasks implement the music library: a self-hosted music streaming server
at `/music/` backed by Navidrome. The operator uploads audio files via the
admin UI or `scp`; patrons can browse albums and stream tracks directly from
their browser or a Subsonic-compatible app.

The music library is the data foundation for Stage 5 (Jukebox). Complete this
stage first.

Complete tasks in the order they are numbered. Each task is scoped to
approximately one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 0 and Stage 1 tasks must be complete before
starting Stage 4.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│ nginx                                           │
│  /music    → 301 /music/                       │
│  /music/   → proxy to navidrome:4533           │
└────────────────────┬────────────────────────────┘
                     │ HTTP reverse proxy
┌────────────────────▼────────────────────────────┐
│ navidrome.service                               │
│  • Web UI + Subsonic API on 127.0.0.1:4533     │
│  • Scans /srv/cafebox/navidrome/music/          │
│  • Stores metadata DB in /srv/cafebox/navidrome/│
└────────────────────┬────────────────────────────┘
                     │ reads audio files
┌────────────────────▼────────────────────────────┐
│ /srv/cafebox/navidrome/                         │
│   music/        ← operator uploads here        │
│   navidrome.db  ← SQLite metadata / scan cache │
└─────────────────────────────────────────────────┘
```

**Design decisions:**
- **Navidrome** is chosen for its low resource use (single Go binary, ≈ 50 MB
  RAM at rest), ARM support, clean web UI, and Subsonic API compatibility with
  mobile apps (DSub, Symfonium, etc.).
- **No transcoding on Pi Zero 2W.** The Pi Zero 2W has insufficient CPU for
  real-time transcoding. Navidrome is configured with `TranscodingCacheSize=0`
  and transcoding disabled. Audio files should be uploaded in a format browsers
  can play natively (MP3, OGG, AAC, FLAC).
- **Public read-only access.** Navidrome is configured with a shared guest
  account that has stream-only access. The admin account is for library
  management. Patron-facing access requires no login.
- **Scan on startup + rescan API.** Navidrome scans the music directory at
  startup and exposes a `/api/admin/services/navidrome/rescan` endpoint for
  triggering a rescan after new uploads.

---

## Task 4.01 — Navidrome Installation

Download and install the Navidrome binary for the target architecture.

Navidrome releases static binaries for linux/arm (armv7) and linux/arm64
on GitHub at `navidrome/navidrome`.

**Deliverables:**
- `ansible/roles/navidrome/tasks/main.yml` — implement the placeholder:
  - Create `navidrome` system user and group.
  - Detect architecture and download the correct Navidrome release binary
    to `/usr/local/bin/navidrome`.
  - Set `mode: "0755"`.
  - Ensure `/srv/cafebox/navidrome/` and `/srv/cafebox/navidrome/music/`
    exist and are owned by `navidrome:navidrome`.
- `ansible/roles/navidrome/vars/main.yml` — pin the Navidrome version.

**Acceptance criteria:**
- `/usr/local/bin/navidrome --version` succeeds on both `armv7l` and `x86_64`.
- Music storage directories exist and are writable by the `navidrome` user.
- Tests pass: binary exists; storage directories exist.

---

## Task 4.02 — Navidrome Configuration

Write the Navidrome configuration file. Navidrome reads a TOML config file
(or environment variables).

**Deliverables:**
- `ansible/roles/navidrome/templates/navidrome.toml.j2`:
  ```toml
  MusicFolder = "/srv/cafebox/navidrome/music"
  DataFolder  = "/srv/cafebox/navidrome"
  Address     = "127.0.0.1"
  Port        = 4533
  BaseUrl     = "/music"

  # Disable transcoding — Pi Zero 2W has insufficient CPU
  TranscodingCacheSize = "0"

  # Allow unauthenticated guest streaming
  EnableGuestUser = true
  ```
- Tasks deploy the config to `/etc/navidrome/navidrome.toml`, owned by
  `root`, readable by `navidrome`.
- Handler: `Restart navidrome` triggered when config changes.

**Acceptance criteria:**
- Config deploys without errors.
- `BaseUrl = "/music"` ensures Navidrome generates correct internal links
  when served behind the nginx `/music/` prefix.
- Tests pass: config file is deployed; contains `MusicFolder` and `BaseUrl`.

---

## Task 4.03 — navidrome.service Systemd Unit

Create and enable the systemd service.

**Deliverables:**
- `ansible/roles/navidrome/files/navidrome.service`:
  ```ini
  [Unit]
  Description=Navidrome Music Library
  After=network.target

  [Service]
  Type=simple
  User=navidrome
  Group=navidrome
  ExecStart=/usr/local/bin/navidrome --configfile /etc/navidrome/navidrome.toml
  Restart=on-failure
  RestartSec=5
  PrivateTmp=true
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=true
  ReadWritePaths=/srv/cafebox/navidrome

  [Install]
  WantedBy=multi-user.target
  ```
- Tasks deploy and enable the service.

**Acceptance criteria:**
- `navidrome.service` reaches `active (running)` after provision.
- `curl http://127.0.0.1:4533/music/` returns a valid HTTP response.
- Tests pass: service unit exists; contains `PrivateTmp=true`; tasks enable
  the service.

---

## Task 4.04 — nginx Routing

Update the nginx configuration template to reverse-proxy to Navidrome.

Navidrome requires the `BaseUrl` to match the nginx location prefix so that
internally generated links (album art URLs, API paths) resolve correctly.
Ensure headers pass the real host and protocol.

**Location blocks (conditional on `services.navidrome.enabled`):**
- `location = /music` → `return 301 /music/`
- `location /music/` → `proxy_pass http://127.0.0.1:4533`
- Include standard proxy headers: `Host`, `X-Real-IP`, `X-Forwarded-For`,
  `X-Forwarded-Proto`.

**Deliverables:**
- Updated `ansible/roles/nginx/templates/nginx.conf.j2`.

**Acceptance criteria:**
- `curl -I http://cafe.box/music` returns 301 to `/music/`.
- `curl http://cafe.box/music/` returns the Navidrome web UI.
- Album art and audio streaming work through the proxy.
- Blocks are absent when `services.navidrome.enabled: false`.
- Tests pass: rendered config contains the redirect and proxy blocks when
  enabled; both are absent when disabled.

---

## Task 4.05 — Admin Upload Integration

Wire the music library into the admin upload endpoint from Task 1.11 and
add a rescan trigger.

**Deliverables:**
- Verify `ansible/roles/admin/files/backend/routers/upload.py` accepts
  uploads for `service_id = "navidrome"` and writes files to
  `{{ storage.locations.navidrome }}/music/`.
- Allowed extensions: `.mp3`, `.ogg`, `.flac`, `.aac`, `.m4a`, `.opus`.
- `POST /api/admin/services/navidrome/rescan` — triggers
  `sudo systemctl restart navidrome.service` (Navidrome rescans on startup).
- Update `ansible/roles/admin/files/backend/services_map.py`:
  ```python
  "navidrome": {
      "unit": "navidrome.service",
      "name": "Music Library",
      "url_path": "/music/",
  }
  ```
- Update `ansible/roles/admin/templates/sudoers-cafebox.j2` to include
  `navidrome.service` start/stop/restart.

**Acceptance criteria:**
- Uploading an MP3 via `POST /api/admin/upload/navidrome` places the file
  in `/srv/cafebox/navidrome/music/`.
- Uploading a `.exe` returns 422.
- After uploading and calling `/rescan`, the track appears in the Navidrome
  library.
- Tests pass: sudoers template contains `navidrome.service` entries;
  `services_map.py` contains the navidrome entry; upload rejects `.exe`.

---

## Task 4.06 — Portal Tile + cafe.yaml Integration

Wire Navidrome into the portal tile system.

**Deliverables:**
- `ansible/roles/nginx/files/index.html` — ensure the Music tile links
  to `/music/` and is conditionally rendered based on `services.navidrome.enabled`.
- `cafe.yaml` — add a comment to the `navidrome` service entry noting that:
  - No transcoding is performed; upload browser-playable formats (MP3, OGG, FLAC, AAC).
  - Recommended max upload size per file is 50 MB (configurable in nginx if needed).

**Acceptance criteria:**
- Portal tile appears and links to `/music/` when enabled.
- Portal tile is absent when `services.navidrome.enabled: false`.
- Tests pass: public API includes/excludes navidrome tile based on enabled flag.
