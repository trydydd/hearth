# Hearth

A self-contained offline community server running on a **Raspberry Pi Zero 2 W**.
Hearth broadcasts a WiFi hotspot, intercepts captive portal detection, and serves
content through a clean landing page. Each service is an independent systemd unit
routed through a single nginx reverse proxy.

Hearth is a spiritual descendant of **PirateBox**:

- **Offline during operation** — no WAN required; no runtime downloads.
- **Builder can download during build** — CI/local build may fetch upstream releases.
- **Hotspot-only access** — all user traffic arrives via the AP interface.
- **Assume hostile clients** — every connected device is treated as untrusted.
- **Anonymous-by-default for users**, but **hardened-by-default for the box**.
- Content is **curated by the operator** (admin uploads), not an anonymous public dropbox.
- **Prebuilt image** — flash SD card → power on → works.

---

## Quick Start

### 1 — Edit `hearth.yaml`

`hearth.yaml` is the **only file an operator ever needs to edit**. Set the box name,
domain, WiFi credentials, and toggle which services you want.

### 2 — Generate system configs

```bash
make generate-configs
```

This renders all Jinja2 templates in `system/templates/` into `system/generated/`
using the values from `hearth.yaml`.

### 3 — Bootstrap the VM or Pi

```bash
vagrant up         # start the dev VM
vagrant ssh        # open a shell inside the VM
```

### 4 — (Optional) Build a flashable image

```bash
bash image/build.sh
```

See [`image/README.md`](image/README.md) for build prerequisites and flashing instructions.

### 5 — Testing and quality guidelines

See [`TESTING.md`](TESTING.md) for testing layers, role-level validation strategy,
and Python runtime environment standards.

---

## Repository Structure

```
hearth/
├── README.md
├── Vagrantfile                 # Dev VM definition (Vagrant / debian/trixie64)
├── hearth.yaml                   # *** Single user-facing config file ***
├── install.sh                  # Bootstrap script (run on VM or Pi — identical)
├── scripts/
│   ├── dev-hosts.sh            # Adds *.hearth.local to /etc/hosts
│   ├── config.py               # Loads hearth.yaml, used by install.sh + admin backend
│   └── generate-configs.py     # Renders all Jinja2 templates from hearth.yaml
├── image/
│   ├── build.sh                # Builds a flashable .img.xz
│   ├── first-boot.sh           # Runs once on first boot: generates password, sets flag
│   ├── first-boot.service      # systemd oneshot unit that calls first-boot.sh
│   └── README.md               # Instructions for building and flashing the image
├── .github/
│   └── workflows/
│       └── build-image.yml     # GitHub Action: builds and publishes image on tag
├── system/
│   ├── templates/              # Jinja2 templates — never edit these directly
│   └── generated/              # Auto-generated — never edit directly
├── storage/
│   └── setup-symlinks.py       # Creates /srv/hearth/* symlinks from hearth.yaml
├── services/
│   ├── conduit/                # Matrix homeserver
│   ├── element-web/            # Matrix web client
│   ├── calibre-web/            # eBook library
│   ├── kiwix/                  # Offline Wikipedia / ZIM reader
│   └── navidrome/              # Music streaming server
├── admin/
│   ├── backend/                # Admin API (FastAPI)
│   └── frontend/               # Admin web UI
└── portal/
    └── index.html              # Landing page served to hotspot clients
```

---

## Configuration Reference

`hearth.yaml` contains four top-level sections:

| Section | Purpose |
|---------|---------|
| `box` | Identity: `name`, `domain`, `ip` |
| `wifi` | Hotspot: SSID, passphrase, interface, channel, DHCP range |
| `storage` | Base path and per-service data directories |
| `services` | Per-service `enabled` flags |

All system-level configs (nginx, hostapd, dnsmasq, nftables) are **auto-generated**
from `hearth.yaml` by `scripts/generate-configs.py`. Never edit files in
`system/generated/` by hand.

### Storage locations

All writable service data lives under `storage.base` (default `/srv/hearth`),
making backup and migration simple: `rsync /srv/hearth/` captures everything, and
moving to an external drive requires updating only `storage.base` in `hearth.yaml`
and re-provisioning.

| Path (default) | Service | Data stored |
|----------------|---------|-------------|
| `/srv/hearth/conduit` | Conduit (Matrix homeserver) | SQLite/RocksDB database, room state, media uploads, session keys |
| `/srv/hearth/calibre` | Calibre-Web | eBook library (`metadata.db`), user database, cover images, uploaded books |
| `/srv/hearth/kiwix` | Kiwix | Downloaded ZIM files (offline Wikipedia, etc.) — can be 10–100 GB each |
| `/srv/hearth/navidrome` | Navidrome | Music library database, scan cache, transcoding state |

---

## Services

| Service | Description | Port |
|---------|-------------|------|
| [Conduit](https://conduit.rs) | Matrix homeserver | 6167 |
| [Element Web](https://element.io) | Matrix web client | 8080 |
| [Calibre-Web](https://github.com/janeczku/calibre-web) | eBook library | 8083 |
| [Kiwix](https://kiwix.org) | Offline Wikipedia / ZIM reader | 8888 |
| [Navidrome](https://navidrome.org) | Music streaming server | 4533 |

All services are reverse-proxied through nginx on port 80 and reachable at
`http://<box.domain>/<service-path>/`.

---

### Accessing the Portal

Open **http://localhost:8080** in your browser once `vagrant up` completes.

On the very first boot the portal shows a yellow **First Boot Setup** banner
with the generated admin password. The banner disappears after a reboot because
`/run` is a tmpfs that is cleared on every boot.

**VM already running? Reset and re-trigger first-boot:**

```bash
vagrant ssh -c "sudo rm -f /var/lib/hearth/first-boot-done && sudo systemctl start hearth-first-boot.service"
```

Then refresh **http://localhost:8080**.

**Read the password directly from the VM:**

```bash
vagrant ssh -c "sudo cat /run/hearth/initial-password"
```

---

### Developer Workflow

```bash
vagrant up                                                    # Start the dev VM
vagrant halt                                                  # Stop the dev VM
vagrant ssh                                                   # SSH into the dev VM
vagrant destroy -f                                            # Delete the dev VM
vagrant ssh -c "journalctl -f -u 'hearth-*'"                # Tail service logs
```

For testing strategy, role-level validation, and Python runtime standards, see
[`TESTING.md`](TESTING.md).

### Local DNS

To resolve `*.hearth.local` from your development machine:

```bash
sudo bash scripts/dev-hosts.sh add     # add entries to /etc/hosts
sudo bash scripts/dev-hosts.sh remove  # remove them
```

---

## Network & Security Model

- **No WAN routing/NAT** for clients — the box is not an internet gateway.
- **Default-deny firewall** (nftables) — only DHCP (UDP 67/68), DNS (UDP/TCP 53),
  and HTTP (TCP 80) are allowed from the AP interface.
- **AP client isolation** enabled where supported by the hardware.
- Admin UI is reachable from the hotspot but is **not linked** from the portal.
- First-boot generates a random 12-character admin password displayed on the portal
  banner until the operator changes it.

---

## Build-time vs Runtime

| Phase | Responsibility |
|-------|---------------|
| **Build-time (CI/builder)** | Download upstream releases, package everything into the image |
| **Runtime (deployed box)** | No WAN needed. Render configs, manage services, handle uploads |

The resulting image is **fully self-contained** — no internet access is required
after flashing.

## Ansible Role Boundaries

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for architectural and code-organization
principles, including role boundaries and dependency ownership.

---

## Stages

| Stage | Description |
|-------|-------------|
| **Stage 0** | Base infrastructure: config system, templates, networking, image builder |
| **Stage 1** | Admin UI: FastAPI backend + web frontend, authentication |
| **Stage 2** | Matrix Chat: Conduit homeserver + Element Web client |

---

## License

This project is provided as-is for personal and community use.
