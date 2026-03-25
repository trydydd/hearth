# Admin Role

Deploys the Hearth admin backend (FastAPI/uvicorn) and frontend (static HTML),
wires them together behind nginx, and sets up the `hearth-admin` system account
with the minimal sudo permissions the service needs.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (LAN)                                                  │
│  /admin/login.html   /admin/dashboard.html   /admin/upload.html │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (port 80)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  nginx                                                          │
│                                                                 │
│  /admin/*          →  /var/www/hearth/admin/   (static files)  │
│  /api/*            →  127.0.0.1:8000            (proxy_pass)    │
│  /healthz          →  127.0.0.1:8000            (proxy_pass)    │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP (loopback only)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  uvicorn / FastAPI  (user: hearth-admin, port 8000)            │
│                                                                 │
│  routers/public.py    GET  /api/public/services/status          │
│  routers/auth.py      POST /api/admin/login                     │
│                       POST /api/admin/logout                    │
│                       POST /api/admin/auth/change-password      │
│  routers/services.py  GET  /api/admin/services/status           │
│                       POST /api/admin/services/{id}/start       │
│                       POST /api/admin/services/{id}/stop        │
│                       POST /api/admin/services/{id}/restart     │
│  routers/upload.py    POST /api/admin/upload/{service_id}       │
└───┬──────────────┬──────────────────────────────┬──────────────┘
    │              │                              │
    ▼              ▼                              ▼
 hearth.yaml      PAM                       sudo systemctl
 (config)   (password auth)           (service management)
```

### Why nginx in front of uvicorn?

Uvicorn binds only to `127.0.0.1:8000` and is never exposed directly.
nginx handles:

- Serving the static frontend files without involving Python
- TLS termination (if added later)
- The `proxy_pass` to the backend with consistent path rewriting
- Serving the static `/run/hearth/portal-status.json` on the portal
  path while the backend is starting up

---

## Information Flow

### First Boot

On the very first boot, `hearth-first-boot.service` runs
`first-boot.sh` **once** (guarded by `/var/lib/hearth/first-boot-done`):

```
hearth-first-boot.service
  │
  ├─ generate 12-char random alphanumeric password
  ├─ /usr/sbin/chpasswd  →  sets hearth-admin system account password
  ├─ write /run/hearth/initial-password  (mode 0400, owner hearth-admin)
  └─ touch /var/lib/hearth/first-boot-done  (idempotency guard)
```

The browser login flow then detects and handles first boot automatically:

```
Browser                         Backend                      System
   │                               │                            │
   ├─ GET /api/public/             │                            │
   │     services/status ─────────>│                            │
   │                               ├─ first_boot_marker exists? │
   │<── { first_boot: true,        │                            │
   │      initial_password: "…" } ─┤                            │
   │                               │                            │
   │  (shows banner + pre-fills    │                            │
   │   password field)             │                            │
   │                               │                            │
   ├─ POST /api/admin/login ───────>│                            │
   │   X-CSRF-Token: <token>       ├─ pam.authenticate() ──────>│
   │   { password: "…" }           │<── success ────────────────┤
   │<── hearth_session cookie ────┤                            │
   │                               │                            │
   │  (change-password panel       │                            │
   │   shown in browser)           │                            │
   │                               │                            │
   ├─ POST /api/admin/auth/        │                            │
   │     change-password ──────────>│                            │
   │   { current_password: "…",    ├─ pam.authenticate() ──────>│
   │     new_password: "…" }       │<── success ────────────────┤
   │                               ├─ sudo /usr/sbin/chpasswd ─>│
   │                               ├─ unlink initial-password   │
   │<── { status: "ok" } ─────────┤                            │
   │                               │                            │
   └─ redirect → /admin/dashboard  │                            │
```

### Normal Login

```
Browser                         Backend
   │                               │
   ├─ GET /healthz ───────────────>│  (seeds csrf_token cookie)
   │<── csrf_token cookie ─────────┤
   │                               │
   ├─ POST /api/admin/login ───────>│
   │   X-CSRF-Token: <token>       ├─ verify CSRF (double-submit)
   │   { username: "…",            ├─ ignore submitted username
   │     password: "…" }           ├─ pam.authenticate("hearth-admin", pw)
   │<── hearth_session cookie ────┤  (signed, 24 h, HttpOnly)
   │                               │
   └─ redirect → /admin/dashboard  │
```

### Service Management (Dashboard)

```
Browser                         Backend                      systemd
   │                               │                            │
   ├─ GET /api/admin/              │                            │
   │     services/status ──────────>│                            │
   │   hearth_session cookie      ├─ verify session            │
   │   X-CSRF-Token: <token>       ├─ systemctl is-active ─────>│
   │                               │  (per service, no sudo)    │
   │<── [{ id, name,               │<── active/inactive ─────────┤
   │       enabled, running }] ────┤                            │
   │                               │                            │
   ├─ POST /api/admin/services/    │                            │
   │     kiwix/restart ────────────>│                            │
   │                               ├─ verify session + CSRF     │
   │                               ├─ sudo systemctl restart ──>│
   │                               │     kiwix.service          │
   │<── { status: "restarted" } ───┤                            │
```

---

## Security Design

### Username is always `hearth-admin`

The username submitted in the login form is **ignored**. Authentication
is always performed against the `hearth-admin` system account regardless
of what the browser sends. This prevents:

- Username enumeration (an attacker cannot probe whether other system
  accounts exist by trying different usernames)
- Credential stuffing against arbitrary system accounts

### CSRF — double-submit cookie pattern

`GET /healthz` (hit automatically by the frontend on page load) issues a
random `csrf_token` cookie. Every state-changing request must echo that
value back in an `X-CSRF-Token` header. The server compares them with
`secrets.compare_digest` to prevent timing attacks.

The `csrf_token` cookie is intentionally **not** `HttpOnly` — the
JavaScript frontend must be able to read it to include it in the header.
The session cookie (`hearth_session`) **is** `HttpOnly`.

### Session cookies — signed, stateless

Sessions use `itsdangerous.URLSafeTimedSerializer` with a secret key from
`HEARTH_SECRET_KEY`. The signed token is stored entirely in the cookie;
no server-side session store is needed. Tokens expire after 24 hours.

Both cookies use `SameSite=Strict`. `Secure=False` is intentional: the
admin UI is served over plain HTTP on the local hotspot LAN. Setting
`Secure=True` would prevent browsers from sending the cookies at all over
HTTP, breaking the login flow.

### PAM for password verification

`crypt` and `spwd` were removed in Python 3.13 (PEP 594). PAM is the
correct modern method and works on Raspberry Pi OS Trixie (Debian 13).
The `python-pam` package wraps `libpam` via ctypes — no external process
is spawned for authentication.

### sudo scope

`hearth-admin` is granted exactly two categories of sudo commands (see
`templates/sudoers-hearth.j2`):

| Command | Why sudo is needed |
|---|---|
| `/usr/sbin/chpasswd` | Writing `/etc/shadow` requires root |
| `systemctl start\|stop\|restart <unit>` | Managing system units requires root |

`systemctl is-active` does **not** require sudo and is called directly.

`NoNewPrivileges=true` was intentionally **not** set on the service unit
because it would silently block all `sudo` calls, making the sudoers
allowlist unreachable. The sudoers file is the security boundary.

---

## File Layout (deployed)

```
/opt/hearth/admin/
  venv/                    Python virtualenv
  backend/                 FastAPI application
    main.py
    auth.py                PAM password verification helper
    config.py              hearth.yaml loader
    csrf.py                Double-submit CSRF middleware
    session.py             Signed-cookie session helpers
    services_map.py        Service identity map (tile IDs → units)
    routers/
      auth.py              /api/admin/login|logout|change-password
      public.py            /api/public/services/status
      services.py          /api/admin/services/*
      upload.py            /api/admin/upload/*

/var/www/hearth/admin/    Static frontend (served by nginx)
  login.html
  dashboard.html
  upload.html

/etc/hearth/admin.env     HEARTH_SECRET_KEY (mode 0640)
/etc/sudoers.d/hearth     sudo allowlist for hearth-admin
/run/hearth/
  initial-password         Temp password file (first-boot only, 0400)
  portal-status.json       Static fallback for portal (nginx)
/var/lib/hearth/
  first-boot-done          Idempotency flag for first-boot.service
```

---

## Development Setup

```bash
# From repository root
python3 -m venv .venv
source .venv/bin/activate
pip install -r ansible/roles/admin/files/backend/requirements.txt

cd ansible/roles/admin/files/backend
HEARTH_SECRET_KEY=dev uvicorn main:app --reload
```

Do not create a local `.venv` inside `files/backend/` — role payload
directories are deployable artifacts and should stay free of local runtime
state.

The server listens on `http://127.0.0.1:8000`. Interactive API docs are
available at `/docs` (Swagger) and `/redoc`.

## Running the Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

## Configuration

`hearth.yaml` is resolved in this order:

1. Explicit `path` argument to `load_config()`
2. `HEARTH_CONFIG` environment variable
3. `hearth.yaml` in the current working directory

```bash
HEARTH_CONFIG=/etc/cafe/hearth.yaml uvicorn main:app
```

## Regenerating the OpenAPI Schema

```bash
cd ansible/roles/admin/files/backend
python3 -c "
from main import app
import json
schema = app.openapi()
with open('openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)
    f.write('\n')
"
```
