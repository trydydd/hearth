# Stage 2 — Hearth Chat Tasks

These tasks implement a custom ephemeral chat server for Hearth. Messages are stored
in a SQLite database on a dm-crypt encrypted volume whose key is generated at boot and
never written to disk. When the box powers off, the key is gone and the message history
is permanently unrecoverable.

The chat UI is a bespoke single-page application served at `/chat/`, communicating
with the server over a WebSocket at `/chat/ws`. No third-party chat protocols (Matrix,
XMPP) are used.

Complete tasks in the order they are numbered. Each task is scoped to approximately
one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 0 and Stage 1 tasks must be complete before starting Stage 2.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│ nginx                                           │
│  /chat     → 301 /chat/                        │
│  /chat/    → static frontend files             │
│  /chat/ws  → proxy to hearth-chat:8765         │
└────────────────────┬────────────────────────────┘
                     │ WebSocket
┌────────────────────▼────────────────────────────┐
│ hearth-chat.service  (Python / FastAPI)         │
│  • WebSocket hub — broadcast to all clients     │
│  • Enforces unique nicknames per session        │
│  • Reads/writes SQLite on encrypted volume      │
│  • Prunes messages older than 24 h on write     │
└────────────────────┬────────────────────────────┘
                     │ SQLite
┌────────────────────▼────────────────────────────┐
│ /srv/cafebox/chat-data/   (ext4, dm-crypt)      │
│  Encrypted with a random key generated at boot. │
│  Key is never written to disk — lives only in   │
│  RAM. Volume and all messages are unrecoverable │
│  after power-off.                               │
└─────────────────────────────────────────────────┘
```

**Design decisions:**
- **Single room** to start; room infrastructure designed to support expansion.
- **Message history on join:** clients receive the last 100 messages on connect.
- **Unique nicknames:** server rejects connection if the chosen name is already held
  by an active session.
- **No accounts, no passwords:** users enter only a nickname.
- **dm-crypt plain mode** (not LUKS): no key material stored on disk at all.
- **256 MB backing file** (sparse): negligible real disk cost until written.
- **24-hour message TTL:** messages older than 24 hours are pruned on write.

---

## Task 2.01 — Ephemerality Policy Documentation

Document the privacy model clearly so users understand what protection they have and
what they do not.

**Deliverables:**
- `ansible/roles/chat/files/PRIVACY.md` in plain language covering:
  - Messages are stored in RAM-equivalent encrypted storage, not plain disk.
  - Messages are permanently deleted when the box restarts or powers off.
  - The box operator cannot read messages after a reboot.
  - Messages are **not** end-to-end encrypted — the server can read them while
    the box is running if it is compromised.
  - No accounts, no personal data collected beyond the chosen nickname.
- A one-sentence notice added near the chat tile in `ansible/roles/nginx/files/index.html`.

**Acceptance criteria:**
- `PRIVACY.md` uses non-technical language suitable for end users.
- Privacy notice is visible on the portal without clicking through.
- Tests pass: `PRIVACY.md` exists and contains required sections; notice is present
  in `index.html`.

---

## Task 2.02 — Encrypted Volume Service

Create the systemd service that sets up the ephemeral encrypted volume at boot.

The volume is backed by a pre-allocated sparse file at `/srv/cafebox/chat.img`.
At boot the service:
1. Cleans up any stale state from an unclean shutdown — unconditionally unmounts
   `/srv/cafebox/chat-data/` and closes any existing `chat-volume` dm-crypt mapping,
   ignoring errors. This ensures only one mapping ever exists regardless of prior
   shutdown behaviour.
2. Generates a 32-byte random key from `/dev/urandom` — key is never written to disk.
3. Opens an encrypted dm-crypt (plain mode) device using that key.
4. Formats the device as ext4 (run every boot — contents are ephemeral by design).
5. Mounts the device at `/srv/cafebox/chat-data/`.

On stop/reboot the volume is unmounted and the dm-crypt mapping is closed. Without
the key, the ciphertext in `chat.img` is unrecoverable.

**Deliverables:**
- `ansible/roles/chat/files/hearth-volume.service` — systemd `Type=oneshot`
  `RemainAfterExit=yes` unit.
- `ansible/roles/chat/tasks/main.yml` — creates the sparse backing file (if absent),
  installs and enables the service.

**Acceptance criteria:**
- Service reaches `active (exited)` after starting.
- `/srv/cafebox/chat-data/` is a mounted ext4 filesystem after the service runs.
- After stopping the service, the mount is gone and the dm-crypt mapping is removed.
- `chat.img` exists on disk; its contents are unreadable without the key.
- Starting the service a second time (simulating a reboot after unclean shutdown)
  succeeds cleanly without manual intervention.
- Tests pass: backing file exists; service unit contains `RemainAfterExit=yes`;
  tasks enable `hearth-volume.service`.

---

## Task 2.03 — Chat Server

Implement the Python WebSocket chat server as a FastAPI application.

**Behaviour:**
- On connect: client sends `{"type": "join", "nick": "<name>"}`.
  - Server rejects with close code 4001 if the nickname is already active.
  - Server sends the last 100 messages from SQLite to the joining client.
  - Server broadcasts a `{"type": "joined", "nick": "<name>"}` event to all others.
- On message: client sends `{"type": "msg", "text": "<content>"}`.
  - Server stores in SQLite, prunes messages older than 24 h, broadcasts to all.
- On disconnect: server releases the nickname and broadcasts a `left` event.

**Database schema (SQLite, `/srv/cafebox/chat-data/chat.db`):**
```sql
CREATE TABLE messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    room      TEXT    NOT NULL DEFAULT 'general',
    nick      TEXT    NOT NULL,
    text      TEXT    NOT NULL,
    ts        INTEGER NOT NULL  -- Unix timestamp (seconds)
);
```

The `room` column is included now so multi-room support can be added later without
a schema migration.

**Deliverables:**
- `ansible/roles/chat/files/server/main.py`
- `ansible/roles/chat/files/server/requirements.txt`
- `ansible/roles/chat/files/hearth-chat.service` — systemd unit, `After=hearth-volume.service`
- Tasks in `ansible/roles/chat/tasks/main.yml` deploy and enable the service.

**Acceptance criteria:**
- Server starts and listens on `127.0.0.1:8765`.
- Duplicate nickname is rejected with close code 4001.
- Joining client receives message history before any new messages.
- Messages are stored and pruned correctly.
- `Restart=on-failure`, `PrivateTmp=true`, `NoNewPrivileges=true` in service unit.
- Tests pass: server unit exists and contains required hardening directives; tasks
  deploy and enable `hearth-chat.service`; service declares `After=hearth-volume.service`.

---

## Task 2.04 — Chat Frontend

Implement the single-page chat UI served as static files at `/chat/`.

**Flow:**
1. User lands on `/chat/` — sees a nickname entry screen.
2. User enters a nickname and clicks Join (or presses Enter).
3. Client opens WebSocket to `/chat/ws`, sends `join` message.
4. If rejected (nick taken), an inline error is shown — user can try another name.
5. On success, the chat room is shown:
   - Message history loads immediately.
   - Input field at the bottom for sending messages.
   - Connected-user list or join/leave notices (design choice).

**Design requirements:**
- Uses `hearth.css` for all tokens and shared components — no inline styles for
  colours, spacing, or typography.
- Respects `prefers-color-scheme` via the token system (no extra JS needed).
- Pixel-art aesthetic consistent with the portal.
- No external requests — no CDN fonts, no analytics, no third-party scripts.
- Accessible: keyboard-navigable, ARIA labels on interactive elements.

**Deliverables:**
- `ansible/roles/chat/files/frontend/index.html`
- Tasks deploy frontend files to `/var/www/hearth/chat/`.

**Acceptance criteria:**
- Nickname screen is shown on first load.
- Rejected nickname displays an inline error without a page reload.
- Message history appears before the input is enabled.
- Page is functional with JavaScript enabled and degrades gracefully (shows an
  error message) without WebSocket support.
- Tests pass: `index.html` exists; references `/hearth.css`; contains WebSocket
  connection logic targeting `/chat/ws`.

---

## Task 2.05 — nginx Routing

Update the nginx configuration template to serve the chat frontend and proxy
the WebSocket connection.

**Location blocks (conditional on `services.chat.enabled`):**
- `location = /chat` → `return 301 /chat/`
- `location /chat/` → static files at `/var/www/hearth/chat/`
- `location /chat/ws` → `proxy_pass http://127.0.0.1:8765`; WebSocket upgrade headers.

**Deliverables:**
- Updated `ansible/roles/nginx/templates/nginx.conf.j2`.

**Acceptance criteria:**
- `curl -I http://cafe.box/chat` returns a 301 redirect to `/chat/`.
- `curl http://cafe.box/chat/` returns the frontend HTML.
- WebSocket handshake succeeds at `ws://cafe.box/chat/ws`.
- Location blocks are absent when `services.chat.enabled: false`.
- Tests pass: rendered config contains `= /chat` redirect, `/chat/` static block,
  and `/chat/ws` proxy block when enabled; all three are absent when disabled.

---

## Task 2.06 — Portal Tile + Admin Integration

Wire the chat service into the portal tile system and admin backend.

**Deliverables:**
- `ansible/roles/admin/files/backend/services_map.py` — add `chat` entry:
  ```python
  "chat": {
      "unit": "hearth-chat.service",
      "name": "Chat",
      "url_path": "/chat/",
  }
  ```
- `ansible/roles/admin/templates/sudoers-cafebox.j2` — add `start/stop/restart`
  for `hearth-chat.service` and `hearth-volume.service`.
- `cafe.yaml` — add `services.chat.enabled: true` with a comment explaining the
  ephemerality guarantee.
- `ansible/site.yml` — add `chat` role.

**Acceptance criteria:**
- `/api/public/services/status` includes the chat tile when `services.chat.enabled: true`.
- `/api/public/services/status` omits the chat tile when `services.chat.enabled: false`.
- Admin can start/stop/restart `hearth-chat.service` via the admin API.
- Tests pass: public API includes/excludes tile correctly; sudoers template contains
  `hearth-chat.service` and `hearth-volume.service` entries.
