# Stage 5 — Jukebox Tasks

These tasks implement the Hearth Jukebox: a communal song queue that lets
cafe patrons browse the music library, submit tracks to a shared queue, and
listen together. Everyone connected to the WiFi hears the same song at the
same position — like a real jukebox.

Complete tasks in the order they are numbered. Each task is scoped to
approximately one hour of work for an intermediate software engineer.

**Prerequisites:** All Stage 4 tasks must be complete before starting Stage 5.
The music library must be populated with at least a few tracks before testing.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│ nginx                                           │
│  /jukebox     → 301 /jukebox/                  │
│  /jukebox/    → static frontend                │
│  /jukebox/ws  → proxy to hearth-jukebox:8766   │
│  /jukebox/stream → proxy to hearth-jukebox:8766│
└────────────────────┬────────────────────────────┘
                     │
          ┌──────────┴──────────┐
          │ WebSocket           │ HTTP audio stream
          ▼                     ▼
┌─────────────────────────────────────────────────┐
│ hearth-jukebox.service  (Python / FastAPI)      │
│                                                 │
│  Queue management                               │
│   • SQLite queue table (song path, submitted    │
│     by nick, timestamp)                         │
│   • WebSocket hub — broadcasts queue state and  │
│     playback position to all clients            │
│                                                 │
│  Playback engine                                │
│   • Advances queue when current track ends      │
│   • Tracks elapsed seconds of current song      │
│   • GET /jukebox/stream — streams current song  │
│     with Range support; client seeks to server- │
│     reported position on connect                │
└────────────────────┬────────────────────────────┘
                     │ reads files
┌────────────────────▼────────────────────────────┐
│ /srv/cafebox/navidrome/music/                   │
│  (shared read-only access — navidrome owns it)  │
└─────────────────────────────────────────────────┘
```

**Design decisions:**

- **Synchronized playback without Icecast.** Rather than running a full
  Icecast/Liquidsoap stack (heavyweight for a Pi Zero 2W), the server tracks
  how many seconds of the current track have elapsed. When a client connects,
  it receives the elapsed offset and seeks the HTML5 `<audio>` element to that
  position. This gives approximate synchronization (within a second or two)
  across clients without real-time audio multiplexing.
- **Separate service, port 8766.** Keeps the jukebox process isolated from
  hearth-chat. The same service handles both the WebSocket control channel and
  the audio stream endpoint.
- **Read-only access to the music library.** The jukebox process reads files
  from `/srv/cafebox/navidrome/music/` but does not write to the Navidrome
  data directory. Navidrome continues to manage its own database.
- **Queue is ephemeral.** The queue is stored in SQLite in `/tmp` or on the
  ephemeral chat volume. It is intentionally lost on reboot — a clean slate
  each session.
- **Patron nicknames optional.** If the jukebox is embedded in the chat page,
  the patron's chat nickname is used to label submissions. If accessed
  standalone, submission is anonymous.
- **No voting / skip yet.** The queue is strictly ordered; tracks play in
  submission order. Skip functionality (admin only) is an optional extension.

---

## Task 5.01 — Jukebox Service Scaffold

Create the `hearth-jukebox` service: Python / FastAPI, port 8766.

**Deliverables:**
- `ansible/roles/jukebox/files/server/main.py` — FastAPI app with:
  - `GET /jukebox/health` → `{"status": "ok"}`
  - `GET /jukebox/queue` → JSON list of queued tracks with metadata
  - `POST /jukebox/queue` → add a track to the queue (body: `{"path": "..."}`)
  - `GET /jukebox/now-playing` → current track, elapsed seconds, total duration
  - `GET /jukebox/stream` → streams the current audio file with
    `Content-Type: audio/mpeg` (or the appropriate type for the file) and
    `Accept-Ranges: bytes` support for seeking.
  - `WebSocket /jukebox/ws` → real-time queue and playback state events
- `ansible/roles/jukebox/files/server/requirements.txt`:
  ```
  fastapi>=0.111,<1.0
  uvicorn[standard]>=0.29,<1.0
  mutagen>=1.47,<2.0   # audio duration / metadata
  aiofiles>=23.0,<25.0 # async file streaming
  ```
- `ansible/roles/jukebox/files/hearth-jukebox.service`:
  ```ini
  [Unit]
  Description=Hearth Jukebox Service
  After=network.target navidrome.service

  [Service]
  Type=simple
  User=hearth-jukebox
  Group=hearth-jukebox
  WorkingDirectory=/opt/hearth/jukebox/server
  ExecStart=/opt/hearth/jukebox-venv/bin/uvicorn main:app --host 127.0.0.1 --port 8766
  Restart=on-failure
  RestartSec=5
  PrivateTmp=true
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=true
  ReadOnlyPaths=/srv/cafebox/navidrome/music
  ReadWritePaths=/tmp

  [Install]
  WantedBy=multi-user.target
  ```
- `ansible/roles/jukebox/tasks/main.yml`:
  - Create `hearth-jukebox` system user/group.
  - Deploy server files, create virtualenv, install dependencies.
  - Deploy and enable `hearth-jukebox.service`.

**Acceptance criteria:**
- `hearth-jukebox.service` reaches `active (running)`.
- `GET /jukebox/health` returns `{"status": "ok"}`.
- `GET /jukebox/queue` returns an empty list `[]` on a fresh start.
- Tests pass: service unit exists; contains `ReadOnlyPaths=/srv/cafebox/navidrome/music`;
  tasks enable `hearth-jukebox.service`.

---

## Task 5.02 — Playback Engine

Implement the server-side playback state machine that advances the queue and
tracks elapsed time.

**State machine:**
- `IDLE` — queue is empty; no audio is playing.
- `PLAYING` — a track is current; elapsed seconds accumulate in real time.
- On track end (elapsed ≥ duration), dequeue the current track and advance
  to the next. If the queue is empty, transition to `IDLE`.
- Use a `asyncio` background task (started with the app lifespan) that
  sleeps in one-second increments, incrementing elapsed time.

**WebSocket events (server → client):**
```jsonc
// When the queue or playback state changes
{"type": "state", "now_playing": {...} | null, "queue": [...]}

// Periodic heartbeat while PLAYING (every 5 s)
{"type": "tick", "elapsed": 42, "duration": 183}
```

**WebSocket events (client → server):**
```jsonc
// Request current state (e.g. on connect)
{"type": "sync"}

// Submit a track
{"type": "enqueue", "path": "relative/path/to/track.mp3", "nick": "alice"}
```

**Deliverables:**
- Playback engine integrated into `main.py`.
- `GET /jukebox/now-playing` reflects live elapsed time.

**Acceptance criteria:**
- Enqueueing a track while `IDLE` transitions to `PLAYING` within 1 second.
- When a track ends, the next queued track starts automatically.
- Two connected WebSocket clients both receive `tick` events within 1 second
  of each other.
- Tests pass: playback transitions from IDLE → PLAYING on enqueue; queue
  advances on track completion.

---

## Task 5.03 — Library Browse API

Expose a read-only endpoint for browsing the music library so the frontend
can present tracks for queuing without embedding Navidrome's admin UI.

**Deliverables:**
- `GET /jukebox/library` — returns a flat list of tracks found in
  `/srv/cafebox/navidrome/music/` (recursive), with metadata extracted by
  `mutagen`:
  ```jsonc
  [
    {
      "path": "Artist/Album/01 - Track.mp3",  // relative to music root
      "title": "Track Title",
      "artist": "Artist Name",
      "album": "Album Name",
      "duration": 183                          // seconds
    }
  ]
  ```
- Results are cached in memory at startup and refreshed when the service
  restarts (no polling). The rescan endpoint from Task 4.05 restarts both
  `navidrome.service` and `hearth-jukebox.service`.
- Update `POST /api/admin/services/navidrome/rescan` to also restart
  `hearth-jukebox.service` so the library cache is refreshed after uploads.

**Acceptance criteria:**
- `GET /jukebox/library` returns all audio files in the music directory.
- After uploading a new file and calling the rescan endpoint, the file
  appears in the library list.
- Files outside the music root are not accessible via this endpoint.
- Tests pass: library endpoint returns only files within the music root;
  metadata fields are present for each track.

---

## Task 5.04 — Audio Streaming Endpoint

Implement `GET /jukebox/stream` to stream the currently playing audio file
with support for range requests (required for HTML5 `<audio>` seeking).

The stream endpoint is distinct from the library browse endpoint: it always
serves the current song. Clients do not select which file to stream — the
server decides.

**Behaviour:**
- Returns 204 No Content when the jukebox is `IDLE`.
- Returns the audio file bytes with `Accept-Ranges: bytes`.
- Honours `Range:` request headers so the browser can seek to the server-
  reported elapsed offset on connect.
- Sets `Content-Type` from the file extension (`audio/mpeg`, `audio/ogg`,
  `audio/flac`, `audio/aac`).
- Uses `aiofiles` for async I/O; does not block the event loop.

**Client-side synchronization flow:**
1. Client calls `GET /jukebox/now-playing` → receives `{elapsed, duration}`.
2. Client calls `GET /jukebox/stream` with `Range: bytes=<byte_offset>` where
   `byte_offset ≈ file_size × (elapsed / duration)` (approximate seeking).
3. Browser's `<audio>` element plays from approximately the correct position.

**Deliverables:**
- Streaming logic integrated into `main.py`.

**Acceptance criteria:**
- `curl -I http://cafe.box/jukebox/stream` returns `200 OK` with
  `Accept-Ranges: bytes` while a track is playing.
- `curl -H "Range: bytes=0-4095" http://cafe.box/jukebox/stream` returns
  `206 Partial Content`.
- The response body is the audio file content (not an HTML error page).
- Tests pass: stream returns 204 when idle; returns 206 on a valid Range request
  while playing.

---

## Task 5.05 — Jukebox Frontend

Implement the single-page jukebox UI at `/jukebox/`.

**Layout:**
- **Now Playing panel** — album art (if available), track title, artist, album,
  a progress bar driven by `tick` events.
- **Queue panel** — ordered list of upcoming tracks with submitter nickname.
- **Library panel** — searchable list of available tracks; each track has an
  "Add to Queue" button.
- **Audio element** — hidden `<audio>` tag that plays `/jukebox/stream`,
  automatically seeks to the server-reported elapsed position on load.

**Design requirements:**
- Uses `hearth.css` for all tokens — pixel-art aesthetic, consistent with chat
  and portal.
- No external resources.
- Responsive: usable on a phone screen (single-column layout on narrow
  viewports).
- Accessible: keyboard-navigable search and queue controls.

**Deliverables:**
- `ansible/roles/jukebox/files/frontend/index.html`
- Tasks deploy frontend to `/var/www/hearth/jukebox/`.

**Acceptance criteria:**
- Now Playing panel updates in real time as the song advances.
- Adding a track from the library appends it to the queue panel immediately
  (optimistic update via WebSocket echo).
- The `<audio>` element begins playing within 2 seconds of page load when a
  song is active.
- Page shows a clear "Jukebox is idle — add a song to get started" state when
  the queue is empty.
- Tests pass: `index.html` exists; references `/hearth.css`; contains
  WebSocket connection logic to `/jukebox/ws`.

---

## Task 5.06 — nginx Routing + Admin Integration

Wire the jukebox service into nginx and the admin panel.

**Location blocks (conditional on `services.jukebox.enabled`):**
- `location = /jukebox` → `return 301 /jukebox/`
- `location /jukebox/ws` → WebSocket proxy to `127.0.0.1:8766`
- `location /jukebox/stream` → proxy to `127.0.0.1:8766`;
  add `proxy_buffering off` to prevent nginx from buffering the audio stream.
- `location /jukebox/` → static frontend files at `/var/www/hearth/jukebox/`

**Deliverables:**
- Updated `ansible/roles/nginx/templates/nginx.conf.j2`.
- `ansible/roles/admin/files/backend/services_map.py` — add jukebox entry:
  ```python
  "jukebox": {
      "unit": "hearth-jukebox.service",
      "name": "Jukebox",
      "url_path": "/jukebox/",
  }
  ```
- `ansible/roles/admin/templates/sudoers-cafebox.j2` — add
  `hearth-jukebox.service` start/stop/restart.
- `cafe.yaml` — add `services.jukebox.enabled: true`.
- `ansible/site.yml` — add `jukebox` role.

**Acceptance criteria:**
- `curl -I http://cafe.box/jukebox` returns 301.
- `curl http://cafe.box/jukebox/` returns the frontend HTML.
- WebSocket handshake succeeds at `ws://cafe.box/jukebox/ws`.
- Admin can start/stop/restart `hearth-jukebox.service` via admin API.
- Tests pass: rendered nginx config contains all four location blocks when
  enabled; sudoers contains `hearth-jukebox.service`; services_map contains
  jukebox entry.

---

## Optional Extension — Chat Integration

If the Hearth Chat (Stage 2) and Jukebox are both enabled, surface the
current track in the chat UI:

- Chat server listens for jukebox `state` events on an internal asyncio
  channel (not a network connection — both processes are on the same host,
  so a Unix socket or shared SQLite table is appropriate).
- When the jukebox advances to a new track, the chat server inserts a system
  message: `♪ Now playing: {title} — {artist} (queued by {nick})`.
- A `/queue <track search>` command in the chat input opens the jukebox queue
  panel (client-side navigation shortcut, no server change needed).

This extension is out of scope for Stage 5 but should be kept in mind when
designing the inter-service communication boundary.
