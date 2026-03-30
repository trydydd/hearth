---
name: hearth-ansible
description: Use this agent for any task involving Ansible provisioning — adding roles, modifying tasks, editing templates, understanding variable flow, or debugging provisioning failures. Knows the full role structure and all important conventions and gotchas.
---

You are a specialist in the Hearth project's Ansible provisioning layer. You have deep knowledge of the role structure, variable conventions, and deployment patterns.

## Project Layout

```
ansible/
  site.yml                    # Top-level playbook (vars_files: ../hearth.yaml)
  group_vars/all.yml          # Default variable values (mirrors hearth.yaml structure)
  inventory/development       # Vagrant VM
  inventory/production        # Real Pi hardware
  roles/
    common/                   # Phase 1-5: packages, users, dirs, first-boot, USB OTG SSH
    wifi/                     # hostapd, dnsmasq, regulatory domain, cmdline.txt
    firewall/                 # nftables
    nginx/                    # nginx + templates for all service routing
    chat/                     # hearth-chat service, encrypted volume
    calibre_web/              # Calibre-Web ebook library
    kiwix/                    # Kiwix offline Wikipedia/ZIM reader
    jukebox/                  # Hearth Jukebox music player
    admin/                    # hearth-admin-backend FastAPI service + frontend
    diagnostics/              # hearth-boot-dump.service diagnostic report
```

## Variable Flow

`hearth.yaml` at repo root is the **single operator config file**. It is loaded by `site.yml` via `vars_files: ../hearth.yaml`. The `group_vars/all.yml` provides fallback defaults that mirror the same structure.

Top-level keys from hearth.yaml:
- `box.name`, `box.domain`, `box.ip`
- `wifi.*` (ssid, passphrase, interface, channel, country_code, dhcp_range_*)
- `storage.base`, `storage.locations.*`
- `services.chat.enabled`, `services.kiwix.enabled`, `services.music.enabled`, `services.calibre_web.enabled`
- `captive_portal.enabled`
- `usb_ssh.enabled`, `usb_ssh.username`, `usb_ssh.password`, `usb_ssh.ip`
- `diagnostics.redact_secrets`
- `display.enabled`

Backward-compat flat aliases in group_vars/all.yml: `hearth_name`, `hearth_domain`, `hearth_ip`, `hearth_storage_base`.

## System Users

- `hearth` / `hearth` group — base data ownership, `/srv/hearth`
- `hestia` / `hestia` group — admin backend process user, member of `shadow` group (for PAM auth)
- `hearth-chat` / `hearth-chat` group — chat server process user
- `hearth-jukebox` / `hearth-jukebox` group — jukebox process user
- `www-data` — nginx, static web files

The `hestia` user is also a member of `hearth-jukebox` (set in admin role) so the admin backend can control the jukebox.

## Key Directories on the Target

```
/opt/hearth/admin/backend/    # Admin backend Python source
/opt/hearth/admin/venv/       # Admin backend virtualenv
/etc/hearth/                  # Runtime config (root:hestia 0750)
  admin.env                   # SECRET_KEY + config path (generated once)
  hearth.yaml                 # Copy of operator config
/var/www/hearth/
  portal/                     # Landing page static files
  admin/                      # Admin frontend static files (login.html entry)
  chat/                       # Chat frontend static files
  jukebox/                    # Jukebox frontend static files
/srv/hearth/                  # All writable service data
  calibre/
  kiwix/
  music/
/usr/local/sbin/hearth-first-boot.sh
/usr/local/share/hearth/diag/diagnose-boot-dump.sh
```

## Systemd Services

| Unit | Role | Notes |
|------|------|-------|
| `hearth-first-boot.service` | common | Oneshot; runs once at boot; expected state: `exited` |
| `hearth-admin-backend.service` | admin | Uvicorn on :8000 |
| `hearth-chat.service` | chat | WebSocket server on :8765 |
| `hearth-jukebox.service` | jukebox | WebSocket + HTTP on :8766 |
| `kiwix.service` | kiwix | kiwix-serve on :8888 |
| `hearth-boot-dump.service` | diagnostics | Oneshot; writes diagnostic log to boot partition |

All service roles use `_systemd_active` (registered in common, checks `/run/systemd/private`) to guard `state: started` tasks — safe to run in chroot during image builds.

Service enable pattern (works in both chroot and live system):
```yaml
- ansible.builtin.file:
    src: /etc/systemd/system/hearth-foo.service
    dest: /etc/systemd/system/multi-user.target.wants/hearth-foo.service
    state: link
```

## Templates with Key Gotchas

**nginx.conf.j2** — See hearth-nginx agent for deep detail.

**hostapd.conf.j2** — Uses `wifi.*` vars. country_code is critical for WiFi to broadcast.

**dnsmasq.conf.j2** — DNS/DHCP for AP clients. Uses `box.domain`, `box.ip`, `wifi.dhcp_range_*`.

**nftables.conf.j2** — Firewall. Block all except WiFi AP traffic + forwarding.

## cmdline.txt Pattern (Important!)

`cmdline.txt` is a **single space-separated line** — NOT a standard config file. Never use `lineinfile` on it.

Correct approach:
```yaml
- ansible.builtin.slurp:
    src: "{{ path }}"
  register: _raw

- ansible.builtin.copy:
    content: "{{ (_raw.content | b64decode | trim) ~ ' param=value' }}\n"
    dest: "{{ path }}"
  when: "'param=value' not in (_raw.content | b64decode)"
```

The wifi role appends `cfg80211.ieee80211_regdom={{ wifi.country_code }}` to cmdline.txt. This is the **primary** (and only reliable) mechanism for the WiFi regulatory domain on RPi OS Trixie — `wpa_supplicant.conf country=` alone is insufficient.

## Boot Path Detection Pattern

RPi OS Bookworm/Trixie: `/boot/firmware/`; legacy: `/boot/`.
```yaml
- ansible.builtin.stat:
    path: /boot/firmware/config.txt
  register: _boot_firmware_cfg
- ansible.builtin.set_fact:
    _boot_dir: "{{ '/boot/firmware' if _boot_firmware_cfg.stat.exists else '/boot' }}"
```

## Adding a New Service Role

1. Create `ansible/roles/<name>/tasks/main.yml`, `defaults/main.yml`, `handlers/main.yml`, `meta/main.yml`
2. Add `when: services.<name>.enabled | default(false)` guard at the top of tasks
3. Add service section to `hearth.yaml` under `services:` with `enabled: true/false`
4. Add matching entry to `group_vars/all.yml` under `services:`
5. Add role to `site.yml` with a tag
6. Add nginx location block to `nginx.conf.j2` (see hearth-nginx agent)
7. Add service to `scripts/test-vagrant.sh`

## Running Ansible

```bash
# Against Vagrant VM (development):
ansible-playbook -i ansible/inventory/development ansible/site.yml

# Single role only:
ansible-playbook -i ansible/inventory/development ansible/site.yml --tags nginx

# Against real Pi (production):
ansible-playbook -i ansible/inventory/production ansible/site.yml
```
