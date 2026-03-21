# diagnostics role

Deploys developer diagnostic scripts into a directory inside the target host.

## Default behaviour

Deployment is **off by default** (`diagnostics_enabled: false`). This means:

- Running `ansible-playbook -i inventory/production site.yml` does **nothing** for
  this role — no files are written to the Pi.
- Running `vagrant up` / `vagrant provision` automatically enables the role because
  the Vagrantfile passes `diagnostics_enabled: true` via `extra_vars`.

## Deployed scripts

| Script | Installed path | Purpose |
|--------|---------------|---------|
| `diagnose-first-boot.sh` | `/usr/local/share/cafebox/diag/diagnose-first-boot.sh` | Checks the full first-boot credential chain: system users → service status & journal → portal root files → portal root HTTP response → API status endpoint → nginx error & access logs → network interfaces → nftables ruleset → listening ports |
| `diagnose-wifi.sh` | `/usr/local/share/cafebox/diag/diagnose-wifi.sh` | Checks the full WiFi AP bringup chain: rfkill → interface → firmware/modules → IP address → regulatory domain → hostapd (config, service, journal) → dnsmasq (config, service) → boot config → network-manager conflicts |

## Running a diagnostic script (development VM)

```bash
vagrant ssh -- sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

### WiFi not broadcasting (Pi Zero 2 W)

If the WiFi network is never broadcast on the Pi:

```bash
# Run directly on the Pi (over serial, USB OTG console, or HDMI+keyboard):
sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh

# Or, if you can reach the Pi over Ethernet/USB-OTG SSH:
ssh pi@<host> sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh

# Save the full output for filing an issue:
ssh pi@<host> "sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh 2>&1" | tee /tmp/cafebox-wifi-diag.txt
```

The script accepts an optional interface name argument (default: `wlan0`):

```bash
sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh wlan0
```

#### What the script checks

| Section | What it checks | Common fix |
|---------|---------------|------------|
| 1. rfkill | Soft/hard WiFi radio block | `rfkill unblock wifi` |
| 2. Interface | `wlan0` (or named interface) present | Firmware / module issue (see §3) |
| 3. Firmware | `brcmfmac` loaded; firmware files present; `dmesg` messages | Check `/lib/firmware/brcm/` |
| 4. IP address + mode | AP IP (`10.0.0.1`) assigned; interface in AP mode | Hostapd not started (see §6) |
| 5. Regulatory domain | Country code set (required for most channels on Pi Zero 2 W) | Add `country_code=XX` to `/etc/hostapd/hostapd.conf` |
| 6. hostapd service | Masked / disabled / not running | `systemctl unmask hostapd && systemctl enable --now hostapd` |
| 7. hostapd journal | Error messages from the last 50 log lines | See journal output |
| 8. hostapd config | Config present; correct interface; `DAEMON_CONF` set | Re-provision or edit config |
| 9. dnsmasq service | Running status | `systemctl enable --now dnsmasq` |
| 10. dnsmasq config | Config present | Re-provision |
| 11. dnsmasq journal | Error messages | See journal output |
| 12. Interfaces | Summary of all network interfaces | — |
| 13. Listening ports | DNS (:53) and DHCP (:67) ports open | — |
| 14. Boot config | `disable_wifi`, country, dtoverlay in `/boot/firmware/config.txt` | Remove `disable_wifi` overlay; set country |
| 15. Conflicts | NetworkManager / wpa_supplicant racing with hostapd | `systemctl stop wpa_supplicant@wlan0` |

#### Key things to check when the WiFi network is not visible

- **Section 1 (rfkill)** — A soft-block silently stops all wireless transmissions. Run
  `rfkill unblock wifi` and retry.
- **Section 2 (interface)** — If `wlan0` does not exist, the firmware may not have
  loaded. Check `dmesg | grep brcmfmac` and section 3.
- **Section 5 (regulatory domain)** — The Pi Zero 2 W **requires** a country code to
  be allowed to transmit on most channels. If the domain is `00` (world/unset),
  add `country_code=GB` (or your country) to `/etc/hostapd/hostapd.conf`.
- **Section 6 (hostapd)** — On Debian/Raspbian, `hostapd` is **masked by default**.
  The Ansible wifi role unmasks it during provisioning; if provisioning was skipped
  or incomplete, run: `sudo systemctl unmask hostapd && sudo systemctl enable --now hostapd`
- **Section 8 (DAEMON_CONF)** — On some Raspbian images, `/etc/default/hostapd` must
  have `DAEMON_CONF="/etc/hostapd/hostapd.conf"` set, otherwise the service starts
  but reads no configuration and creates no AP.
- **Section 14 (boot config)** — `dtoverlay=disable-wifi` in `/boot/firmware/config.txt`
  turns off the radio entirely.
- **Section 15 (conflicts)** — If `wpa_supplicant` or NetworkManager is managing
  `wlan0`, it will conflict with hostapd. Only hostapd should own the AP interface.

Paste the full output into the GitHub issue.

## Running a diagnostic script (development VM — first-boot credential chain)

```bash
vagrant ssh -- sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

### Reading the first-boot output

Key things to check when the portal is not loading in the host browser:

- **Section 7 (portal root)** — `index.html` must be present. If it is missing,
  re-provision: `vagrant provision`.
- **Section 8 (root HTTP)** — `GET http://localhost/ → HTTP 200` must appear. A
  non-200 response means nginx cannot serve the portal page from inside the VM.
- **Section 11 (access log)** — If the log is *empty* after you tried to open the
  portal in a browser, no request has reached nginx. This means VirtualBox port
  forwarding is not delivering traffic. Run `vagrant reload` to re-apply the port
  forward rules.
- **Section 12 (interfaces)** — Shows the actual NIC names in the VM. The
  nftables rules use a negative match (`iifname != "wlan0"`) so they work
  regardless of whether the NIC is called `eth0`, `enp0s3`, or anything else.

## Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `diagnostics_enabled` | `false` | Set to `true` to deploy scripts. Enabled automatically in the dev VM via Vagrantfile. |
| `diagnostics_dir` | `/usr/local/share/cafebox/diag` | Directory on the target host where scripts are installed. |

## Deploying to production (override)

If you need to run a diagnostic script on a real Pi, pass the flag on the command
line — nothing needs to be changed in the playbook or inventory:

```bash
ansible-playbook -i inventory/production site.yml -e diagnostics_enabled=true
```

The scripts are installed to `diagnostics_dir` and can then be run over SSH:

```bash
ssh pi@<host> sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh
ssh pi@<host> sudo /usr/local/share/cafebox/diag/diagnose-first-boot.sh
```

Remove the scripts afterwards if desired:

```bash
ssh pi@<host> sudo rm -rf /usr/local/share/cafebox/diag
```

