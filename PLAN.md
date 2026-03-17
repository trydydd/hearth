# CafeBox — Agent Build Plan

A self-contained offline community server running on a Raspberry Pi Zero 2 W.
Broadcasts a WiFi hotspot, intercepts captive portal detection, and serves
content through a clean landing page. Extensible by design: each service is
an independent systemd unit routed through a single nginx reverse proxy.

This project is a spiritual descendant of **PirateBox**:
- **Offline during operation** (no WAN required; no runtime downloads)
- **Builder can download during build** (CI/local build may fetch upstream releases)
- **Hotspot-only** access (all user traffic arrives via the AP)
- **Assume hostile clients** (treat every connected device as untrusted)
- **Anonymous-by-default for users**, but **hardened-by-default for the box**
- Content is **curated by the operator** (admin uploads), not an anonymous public dropbox
- **Prebuilt image**: flash SD card → power on → works

---

## Repository Structure

```
cafebox/
├── README.md
├── Vagrantfile                 # Dev VM definition (Vagrant / debian/trixie64)
├── cafe.yaml                   # *** Single user-facing config file ***
├── Makefile                    # Dev shortcuts: vm-start, vm-stop, vm-ssh, vm-destroy, logs
├── ansible/                    # Ansible provisioner (dev VM, Pi over SSH, image builds)
│   ├── ansible.cfg
│   ├── site.yml                # Top-level playbook
│   ├── inventory/
│   │   ├── development         # Vagrant dev VM
│   │   └── production          # Real Pi targets
│   ├── group_vars/
│   │   └── all.yml
│   └── roles/
│       ├── common/             # Base packages, system users, directory layout
│       ├── nginx/              # Web server, portal reverse-proxy
│       ├── conduit/            # Matrix homeserver
│       ├── element_web/        # Matrix web client
│       ├── calibre_web/        # eBook library
│       ├── kiwix/              # Offline Wikipedia / ZIM reader
│       ├── navidrome/          # Music streaming server
│       ├── admin/              # Admin backend + frontend
│       ├── wifi/               # hostapd + dnsmasq hotspot
│       └── firewall/           # nftables rules
├── scripts/
│   ├── dev-hosts.sh            # Adds *.cafe.box to /etc/hosts
│   ├── config.py               # Loads cafe.yaml
│   └── generate-configs.py     # Renders all Jinja2 templates from cafe.yaml
├── .github/
│   └── workflows/
│       └── build-image.yml     # GitHub Action: builds and publishes image on tag
└── system/
    ├── templates/              # Jinja2 templates — never edit these directly
    └── generated/              # Auto-generated — never edit directly
```

---

## Build-time vs Runtime Responsibilities

This is a personal project, so keep the workflow simple and pragmatic.

- **Build-time (builder/CI)**
  - Allowed to download upstream releases (Conduit, Element Web, Kiwix tools, Navidrome, etc.)
  - The resulting **image must be self-contained** so the box can run offline
  - Prefer pinned versions for repeatable releases (optional early on, but recommended)

- **Runtime (on the deployed box)**
  - No WAN required
  - No runtime downloads
  - Only render configs, manage services, and handle operator uploads

---

## Central Configuration

**`cafe.yaml`** — The only file an operator ever needs to edit.

All system-level configs are **auto-generated** from this file by `scripts/generate-configs.py` using
Jinja2 templates.

(Example omitted here for brevity; see the repo for the full sample config.)

### Service Identity Map (Naming Consistency)

CafeBox deals with three different “names” for the same conceptual service:

- **Tile id**: what the portal shows and what `/api/public/services/status` returns.
- **systemd unit**: what `systemctl` controls.
- **storage key**: what `storage.locations.*` uses.

APIs use **tile ids**. Internals map tile ids → unit/storage keys.

---

## Stage 0 — Base Infrastructure

### 0.0 — Threat Model & Network Policy (Offline / Hostile Clients / Hotspot Only)

- No WAN routing/NAT for clients.
- Admin reachable from hotspot; portal must not link to admin.
- Default-deny firewall; allow only DHCP/DNS/HTTP on hotspot interface.
- Enable AP client isolation if feasible.

### 0.4 — nginx Captive Portal

Change Android `/generate_204` handler to redirect to the portal:

```nginx
location /generate_204 { return 302 http://{{ box.domain }}/; }
```

### 0.5 — Development VM (Vagrant + Ansible)

The development VM is managed with **Vagrant**. A `Vagrantfile` at the repo root
defines a `debian/trixie64` box and uses Vagrant's built-in Ansible provisioner
to run `ansible/site.yml` — the same playbook used to provision real Pi hardware
over SSH and to build flashable SD card images.

```
vagrant up       # start (provisions on first run via ansible/site.yml)
vagrant halt     # stop
vagrant ssh      # shell into the VM
vagrant destroy  # delete and start fresh
```

`Makefile` targets (`make vm-start`, `make vm-stop`, `make vm-ssh`,
`make vm-destroy`) delegate directly to vagrant. There is no `scripts/vm.sh`.

### 0.6 — Landing Portal

The portal uses `GET /api/public/services/status`.

### 0.8 — First-Boot Credential Generation (Password Banner)

Keep the password banner:
- On a freshly flashed image, generate a random admin password on first boot.
- Display it on the landing page until the operator changes it.

---

## Stage 1 — Admin UI

- Clarify SessionMiddleware is signed-cookie based unless a server-side store is added.
- Add a simple CSRF defense: require CSRF token header on state-changing requests.
- Use a dedicated `cafebox-admin` user; tighten sudoers.

---

## Stage 2 — Matrix Chat (Conduit + Element Web)

### 2.0 — Reality Check: E2EE vs Ephemerality

CafeBox does not promise messages are erased when users disconnect.
