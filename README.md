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

### 2 — Bootstrap the VM or Pi

```bash
vagrant up         # start the dev VM
vagrant ssh        # open a shell inside the VM
```

### 3 — (Optional) Build a flashable image

```bash
bash scripts/build-image.sh
```

See [`image/README.md`](image/README.md) for build prerequisites and flashing instructions.

### 4 — (Optional) Inject content onto a flashed SD card

```bash
# Place .zim files in zims/ and music files in music/, then:
sudo bash scripts/inject-content.sh /dev/mmcblk0
```

### 5 — Testing and quality guidelines

See [`TESTING.md`](TESTING.md) for testing layers, role-level validation strategy,
and Python runtime environment standards.

---

## Repository Structure

```
hearth/
├── README.md
├── Vagrantfile                 # Dev VM definition (Vagrant / debian/trixie64)
├── hearth.yaml                 # *** Single user-facing config file ***
├── ansible/
│   ├── ansible.cfg
│   ├── site.yml                # Top-level playbook
│   ├── inventory/
│   │   ├── development         # Vagrant dev VM
│   │   └── production          # Real Pi targets
│   └── roles/
│       ├── common/             # Base packages, system users, directory layout
│       ├── nginx/              # Web server, portal reverse-proxy
│       ├── wifi/               # hostapd + dnsmasq hotspot
│       ├── firewall/           # nftables rules
│       ├── admin/              # Admin backend (FastAPI) + frontend
│       ├── chat/               # Ephemeral anonymous chat
│       ├── calibre_web/        # eBook library
│       ├── kiwix/              # Offline Wikipedia / ZIM reader
│       ├── jukebox/            # Communal music jukebox
│       └── diagnostics/        # Boot-partition diagnostic report
├── scripts/
│   ├── build-image.sh          # Builds a flashable .img.xz
│   ├── inject-content.sh       # Copies ZIMs and music onto a flashed SD card
│   ├── config.py               # Loads hearth.yaml
│   ├── generate-configs.py     # Renders Jinja2 templates locally (developer preview)
│   └── dev-hosts.sh            # Adds *.hearth.local to /etc/hosts
├── image/
│   └── README.md               # Instructions for building and flashing the image
├── tasks/                      # Stage-by-stage implementation task documents
├── tests/                      # Automated test suite
├── zims/                       # Drop .zim files here (gitignored)
├── music/                      # Drop music files here (gitignored)
└── .github/
    └── workflows/
        └── build-image.yml     # GitHub Action: builds and publishes image on tag
```

---

## Configuration Reference

`hearth.yaml` contains five top-level sections:

| Section | Purpose |
|---------|---------|
| `box` | Identity: `name`, `domain`, `ip` |
| `wifi` | Hotspot: SSID, passphrase, interface, channel, DHCP range |
| `storage` | Base path and per-service data directories |
| `services` | Per-service `enabled` flags and configuration |
| `usb_ssh` | USB OTG SSH access (operator cable access) |

All system-level configs (nginx, hostapd, dnsmasq, nftables) are **auto-generated**
from `hearth.yaml` by Ansible at provision time.

### Storage locations

All writable service data lives under `storage.base` (default `/srv/hearth`),
making backup and migration simple: `rsync /srv/hearth/` captures everything, and
moving to an external drive requires updating only `storage.base` in `hearth.yaml`
and re-provisioning.

| Path (default) | Service | Data stored |
|----------------|---------|-------------|
| `/srv/hearth/calibre` | Calibre-Web | eBook library (`metadata.db`), user database, cover images |
| `/srv/hearth/kiwix` | Kiwix | ZIM files (offline Wikipedia, etc.) — can be 1–90 GB each |
| `/srv/hearth/music` | Jukebox | Music files (MP3, OGG, FLAC, AAC/M4A) |

---

## Services

| Service | Description | Path |
|---------|-------------|------|
| Admin UI | Operator dashboard — password, service management, uploads | `/admin/` |
| Chat | Ephemeral anonymous chat (messages deleted on reboot) | `/chat/` |
| [Calibre-Web](https://github.com/janeczku/calibre-web) | eBook library | `/calibre/` |
| [Kiwix](https://kiwix.org) | Offline Wikipedia / ZIM reader | `/library/` |
| Jukebox | Communal music player with shared queue | `/jukebox/` |

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
| **Stage 2** | Ephemeral Chat: encrypted tmpfs-backed anonymous chat |
| **Stage 3** | Kiwix: offline Wikipedia and ZIM content reader |
| **Stage 4** | Jukebox: communal music player with shared queue |

---

## License

This project is provided as-is for personal and community use.
