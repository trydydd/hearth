#!/usr/bin/env bash
# diagnose-boot-dump.sh — write a comprehensive diagnostic report to the
# FAT32 boot partition so it can be read by pulling the SD card.
#
# Deployed to /usr/local/share/cafebox/diag/ on the target host by the
# diagnostics Ansible role.  Runs automatically on every boot via the
# cafebox-boot-dump.service systemd unit (After=multi-user.target).
#
# Output: /boot/firmware/cafebox-diagnostics.log (modern RPi OS layout)
#         /boot/cafebox-diagnostics.log          (legacy layout)
#
# The report is overwritten on each boot — only the latest state is kept.
#
# When the Pi won't give you a shell (no WiFi, no USB-OTG SSH), pull the
# SD card, mount the FAT32 boot partition on any computer, and read the log.
#
# Secret redaction is controlled by the CAFEBOX_REDACT_SECRETS environment
# variable (set via the systemd unit from cafe.yaml: diagnostics.redact_secrets).
# When "true", passwords and passphrases are replaced with <REDACTED>.

set -euo pipefail

# ---------------------------------------------------------------------------
# Detect boot partition path
# ---------------------------------------------------------------------------
if [ -d /boot/firmware ]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
fi

OUTPUT="${BOOT_DIR}/cafebox-diagnostics.log"

# ---------------------------------------------------------------------------
# Redaction helper
# ---------------------------------------------------------------------------
REDACT="${CAFEBOX_REDACT_SECRETS:-false}"

# Redact a value if redaction is enabled; otherwise print it as-is.
# Usage: maybe_redact "some_secret_value"
maybe_redact() {
    if [ "${REDACT}" = "true" ]; then
        printf '<REDACTED>'
    else
        printf '%s' "$1"
    fi
}

# Show a config file, optionally redacting known secret keys.
# Usage: show_config_file /path/to/file [key_pattern ...]
# key_pattern is a grep -E pattern matching lines whose values should be redacted.
show_config_file() {
    local file="$1"; shift
    if [ ! -f "$file" ]; then
        fail "file not found: $file"
        return
    fi
    if [ "${REDACT}" = "true" ] && [ $# -gt 0 ]; then
        local pattern="$1"
        sed -E "s/^(($pattern)[[:space:]]*[=:][[:space:]]*).+$/\1<REDACTED>/" "$file"
    else
        cat "$file"
    fi
}

# ---------------------------------------------------------------------------
# Output helpers (same style as diagnose-wifi.sh / diagnose-first-boot.sh)
# ---------------------------------------------------------------------------
hr()  { printf '\n%s\n' "──────────────────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$1"; hr; }
ok()  { printf '  [OK]   %s\n' "$1"; }
warn(){ printf '  [WARN] %s\n' "$1"; }
fail(){ printf '  [FAIL] %s\n' "$1"; }

# ---------------------------------------------------------------------------
# Redirect all output to the boot partition log
# ---------------------------------------------------------------------------
exec > "${OUTPUT}" 2>&1

hdr "CafeBox Boot Diagnostics"
printf '  Generated: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '  Redaction: %s\n' "${REDACT}"

# ============================= Section 1 ====================================
hdr "1. System Identity"

printf '  Hostname:  %s\n' "$(hostname 2>/dev/null || echo unknown)"
printf '  Kernel:    %s\n' "$(uname -r)"
printf '  Arch:      %s\n' "$(uname -m)"
printf '  Uptime:    %s\n' "$(uptime -p 2>/dev/null || uptime)"

if [ -f /proc/device-tree/model ]; then
    MODEL="$(tr -d '\0' < /proc/device-tree/model)"
    printf '  Pi model:  %s\n' "$MODEL"
else
    warn "not running on Raspberry Pi hardware (/proc/device-tree/model absent)"
fi

# ============================= Section 2 ====================================
hdr "2. Boot Configuration"

printf '  Boot dir:  %s\n' "${BOOT_DIR}"
echo

printf '  --- config.txt ---\n'
if [ -f "${BOOT_DIR}/config.txt" ]; then
    cat "${BOOT_DIR}/config.txt"
    echo
    # Key checks
    if grep -q "dtoverlay=dwc2" "${BOOT_DIR}/config.txt"; then
        ok "dtoverlay=dwc2 present (USB OTG gadget)"
    else
        fail "dtoverlay=dwc2 MISSING — USB OTG will not work"
    fi
    if grep -q "dtoverlay=disable-wifi" "${BOOT_DIR}/config.txt"; then
        fail "dtoverlay=disable-wifi is set — WiFi is DISABLED by config.txt"
    else
        ok "WiFi not disabled by config.txt"
    fi
else
    fail "config.txt not found at ${BOOT_DIR}/config.txt"
fi

echo
printf '  --- cmdline.txt ---\n'
if [ -f "${BOOT_DIR}/cmdline.txt" ]; then
    cat "${BOOT_DIR}/cmdline.txt"
    echo
    if grep -q "modules-load=dwc2,g_ether" "${BOOT_DIR}/cmdline.txt"; then
        ok "modules-load=dwc2,g_ether present (USB Ethernet gadget)"
    else
        fail "modules-load=dwc2,g_ether MISSING — USB network will not appear"
    fi
else
    fail "cmdline.txt not found at ${BOOT_DIR}/cmdline.txt"
fi

echo
printf '  --- userconf.txt ---\n'
if [ -f "${BOOT_DIR}/userconf.txt" ]; then
    ok "userconf.txt present (RPi OS will create operator user on next boot)"
    show_config_file "${BOOT_DIR}/userconf.txt" ".*"
else
    # RPi OS processes and deletes userconf.txt on first boot — absence after
    # first boot is normal (same as the ssh flag file).  Check whether a
    # non-system operator account (UID 1000–65533) already exists instead.
    if getent passwd 2>/dev/null | awk -F: '$3 >= 1000 && $3 <= 65533' | grep -q .; then
        ok "userconf.txt absent (already processed on first boot — operator user exists)"
    else
        warn "userconf.txt not found and no operator user (UID 1000–65533) found — first-boot user creation may have failed"
    fi
fi

echo
printf '  --- ssh enable file ---\n'
if [ -f "${BOOT_DIR}/ssh" ]; then
    ok "ssh enable file present (will be processed on next boot or is yet to be processed)"
else
    # RPi OS processes the ssh file on first boot — enables SSH then deletes
    # the file.  Absence of the file after first boot is therefore normal.
    # Check the SSH service state to determine the real status.
    SSH_ENABLED="$(systemctl is-enabled ssh 2>/dev/null || echo unknown)"
    if [ "${SSH_ENABLED}" = "enabled" ]; then
        ok "ssh enable file absent (already processed by RPi OS first-boot — SSH service is enabled)"
    else
        warn "ssh enable file not found and SSH service is '${SSH_ENABLED}' — SSH may not be available"
    fi
fi

# ============================= Section 3 ====================================
hdr "3. Kernel Modules"

printf '  USB OTG chain:\n'
for mod in dwc2 g_ether; do
    if lsmod 2>/dev/null | grep -qE "^${mod}([[:space:]]|$)"; then
        ok "module ${mod} loaded (lsmod)"
    elif [ -d "/sys/module/${mod}" ]; then
        # Module is present as a built-in or device-tree-loaded driver.
        # On Pi Zero 2 W, dwc2 is loaded via dtoverlay and may not show in
        # lsmod as a standalone entry but /sys/module/dwc2 will exist.
        ok "module ${mod} present (/sys/module — device-tree loaded or built-in)"
    elif dmesg 2>/dev/null | grep -qiE "(^|[[:space:]])${mod}[[:space:]/:]"; then
        # Fall back to dmesg: any line containing " dwc2 " or " dwc2/" or " dwc2:"
        # (i.e. the module name preceded and followed by non-identifier chars).
        ok "module ${mod} active (confirmed via dmesg)"
    else
        fail "module ${mod} NOT loaded"
    fi
done

echo
printf '  WiFi chain:\n'
for mod in brcmfmac cfg80211; do
    if lsmod 2>/dev/null | grep -q "^${mod}"; then
        ok "module ${mod} loaded"
    else
        fail "module ${mod} NOT loaded"
    fi
done

echo
printf '  Relevant dmesg (dwc2, g_ether, brcmfmac, firmware — last 30 lines):\n'
dmesg 2>/dev/null | grep -iE 'dwc2|g_ether|gadget|brcmfmac|firmware|wlan|usb0' | tail -30 || warn "no relevant dmesg lines found"

# ============================= Section 4 ====================================
hdr "4. Network Interfaces"

printf '  All interfaces:\n'
ip link show 2>/dev/null || warn "ip command not available"

echo
printf '  Interface details:\n'
for iface in wlan0 usb0; do
    echo
    if ip link show "${iface}" &>/dev/null; then
        ok "interface ${iface} exists"
        ip addr show "${iface}" 2>/dev/null || true
    else
        fail "interface ${iface} does NOT exist"
    fi
done

echo
printf '  rfkill status:\n'
if command -v rfkill &>/dev/null; then
    rfkill list all 2>/dev/null || true
    if rfkill list all 2>/dev/null | grep -qA2 "Wireless LAN" | grep -q "Soft blocked: yes"; then
        fail "WiFi is SOFT-BLOCKED"
    fi
    if rfkill list all 2>/dev/null | grep -qA2 "Wireless LAN" | grep -q "Hard blocked: yes"; then
        fail "WiFi is HARD-BLOCKED"
    fi
else
    warn "rfkill not available"
fi

echo
printf '  WiFi interface mode:\n'
if command -v iw &>/dev/null && ip link show wlan0 &>/dev/null; then
    iw dev wlan0 info 2>/dev/null || warn "could not query wlan0 via iw"
    IW_TYPE="$(iw dev wlan0 info 2>/dev/null | awk '/type/{print $2}' || true)"
    if [ "${IW_TYPE}" = "AP" ]; then
        ok "wlan0 is in AP mode"
    elif [ -n "${IW_TYPE}" ]; then
        warn "wlan0 is in ${IW_TYPE} mode (expected AP)"
    fi
else
    warn "iw not available or wlan0 not present"
fi

echo
printf '  NetworkManager conflict check:\n'
if systemctl is-active NetworkManager &>/dev/null; then
    ok "NetworkManager is running"
    NM_UNMANAGED_FILE="/etc/NetworkManager/conf.d/cafebox-wifi.conf"
    if [ -f "${NM_UNMANAGED_FILE}" ]; then
        ok "NM unmanaged config exists: ${NM_UNMANAGED_FILE}"
        cat "${NM_UNMANAGED_FILE}"
    else
        warn "NM unmanaged config NOT found at ${NM_UNMANAGED_FILE}"
        warn "NetworkManager may be managing wlan0 and conflicting with hostapd"
        warn "Fix: re-provision with the wifi Ansible role or create ${NM_UNMANAGED_FILE}"
    fi
else
    ok "NetworkManager is not running (no conflict)"
fi

# ============================= Section 5 ====================================
hdr "5. Systemd Service Status"

SERVICES=(
    "cafebox-first-boot.service"
    "hostapd"
    "dnsmasq"
    "nftables"
    "nginx"
    "ssh"
)

for svc in "${SERVICES[@]}"; do
    ACTIVE="$(systemctl is-active "$svc" 2>/dev/null || echo unknown)"
    ENABLED="$(systemctl is-enabled "$svc" 2>/dev/null || echo unknown)"

    if [ "$ACTIVE" = "active" ] || [ "$ACTIVE" = "inactive" -a "$svc" = "cafebox-first-boot.service" ]; then
        # first-boot is oneshot RemainAfterExit — "inactive" after exit is fine
        ok "${svc}: active=${ACTIVE}  enabled=${ENABLED}"
    elif [ "$ACTIVE" = "inactive" ] && [ "$ENABLED" = "enabled" ]; then
        warn "${svc}: active=${ACTIVE}  enabled=${ENABLED}  (enabled but not running)"
    else
        fail "${svc}: active=${ACTIVE}  enabled=${ENABLED}"
    fi

    # Extra check: is hostapd masked?
    if [ "$svc" = "hostapd" ]; then
        if systemctl is-enabled hostapd 2>&1 | grep -q "masked"; then
            fail "hostapd is MASKED — run: systemctl unmask hostapd"
        fi
    fi
done

# ============================= Section 6 ====================================
hdr "6. Service Configuration Files"

echo
printf '  --- hostapd (/etc/hostapd/hostapd.conf) ---\n'
if [ -f /etc/hostapd/hostapd.conf ]; then
    ok "hostapd.conf exists"
    show_config_file /etc/hostapd/hostapd.conf "wpa_passphrase"
    echo
    # Key value checks
    CONF_IFACE="$(grep -E '^interface=' /etc/hostapd/hostapd.conf 2>/dev/null | cut -d= -f2 | tr -d ' ' || true)"
    CONF_SSID="$(grep -E '^ssid=' /etc/hostapd/hostapd.conf 2>/dev/null | cut -d= -f2 || true)"
    CONF_DRIVER="$(grep -E '^driver=' /etc/hostapd/hostapd.conf 2>/dev/null | cut -d= -f2 || true)"
    CONF_COUNTRY="$(grep -E '^country_code=' /etc/hostapd/hostapd.conf 2>/dev/null | cut -d= -f2 | tr -d ' ' || true)"
    printf '  interface=%s  ssid=%s  driver=%s\n' "$CONF_IFACE" "$CONF_SSID" "$CONF_DRIVER"
    [ "$CONF_IFACE" = "wlan0" ] && ok "interface=wlan0" || warn "interface=${CONF_IFACE} (expected wlan0)"
    [ -n "$CONF_SSID" ] && ok "ssid=${CONF_SSID}" || fail "ssid is empty"
    [ "$CONF_DRIVER" = "nl80211" ] && ok "driver=nl80211" || warn "driver=${CONF_DRIVER} (expected nl80211)"
    if [ -n "$CONF_COUNTRY" ]; then
        ok "country_code=${CONF_COUNTRY} (regulatory domain set)"
    else
        warn "country_code NOT set — Pi Zero 2 W may fail to transmit on most channels"
        warn "Fix: set wifi.country_code in cafe.yaml (e.g. GB, US, DE)"
    fi
    # Check that /etc/default/hostapd points DAEMON_CONF at the config file.
    # If DAEMON_CONF is empty/commented-out, hostapd starts with no config
    # and the AP is never configured — the most common cause of no WiFi.
    DAEMON_CONF_FILE="/etc/default/hostapd"
    if [ -f "${DAEMON_CONF_FILE}" ]; then
        DAEMON_CONF_VAL="$(grep -E '^DAEMON_CONF=' "${DAEMON_CONF_FILE}" 2>/dev/null | cut -d= -f2 | tr -d '"' | tr -d "'" | tr -d ' ' || true)"
        if [ "${DAEMON_CONF_VAL}" = "/etc/hostapd/hostapd.conf" ]; then
            ok "DAEMON_CONF=/etc/hostapd/hostapd.conf (hostapd will read the config)"
        elif [ -n "${DAEMON_CONF_VAL}" ]; then
            warn "DAEMON_CONF=${DAEMON_CONF_VAL} (expected /etc/hostapd/hostapd.conf)"
        else
            fail "DAEMON_CONF not set in ${DAEMON_CONF_FILE} — hostapd starts with NO config file and the AP will NOT broadcast"
            fail "Fix: re-provision with the wifi Ansible role to set DAEMON_CONF"
        fi
    else
        warn "${DAEMON_CONF_FILE} not found (DAEMON_CONF cannot be verified)"
    fi
else
    fail "hostapd.conf NOT found"
fi

echo
printf '  --- dnsmasq (/etc/dnsmasq.d/cafebox.conf) ---\n'
if [ -f /etc/dnsmasq.d/cafebox.conf ]; then
    ok "cafebox dnsmasq config exists"
    cat /etc/dnsmasq.d/cafebox.conf
    echo
    grep -q "address=/#/" /etc/dnsmasq.d/cafebox.conf && ok "DNS catch-all (address=/#/) present" || fail "DNS catch-all MISSING"
    grep -q "dhcp-range=" /etc/dnsmasq.d/cafebox.conf && ok "dhcp-range present" || fail "dhcp-range MISSING"
else
    fail "cafebox dnsmasq config NOT found at /etc/dnsmasq.d/cafebox.conf"
fi

echo
printf '  --- nftables (/etc/nftables.conf) ---\n'
if [ -f /etc/nftables.conf ]; then
    ok "nftables.conf exists"
    cat /etc/nftables.conf
    echo
    grep -q "flush ruleset" /etc/nftables.conf && ok "flush ruleset present" || warn "flush ruleset MISSING"
    grep -q "policy drop" /etc/nftables.conf && ok "input/forward policy drop present" || warn "policy drop MISSING"
else
    fail "nftables.conf NOT found"
fi

echo
printf '  --- nginx ---\n'
if [ -L /etc/nginx/sites-enabled/cafebox.conf ]; then
    ok "/etc/nginx/sites-enabled/cafebox.conf is a symlink"
    ls -la /etc/nginx/sites-enabled/cafebox.conf
elif [ -f /etc/nginx/sites-enabled/cafebox.conf ]; then
    warn "/etc/nginx/sites-enabled/cafebox.conf exists but is NOT a symlink"
else
    fail "/etc/nginx/sites-enabled/cafebox.conf does NOT exist"
fi
if [ -f /etc/nginx/sites-available/cafebox.conf ]; then
    ok "/etc/nginx/sites-available/cafebox.conf exists"
    cat /etc/nginx/sites-available/cafebox.conf
else
    fail "/etc/nginx/sites-available/cafebox.conf NOT found"
fi
if [ -e /etc/nginx/sites-enabled/default ]; then
    warn "default nginx site still enabled (should have been removed)"
else
    ok "default nginx site removed"
fi

# ============================= Section 7 ====================================
hdr "7. CafeBox Application State"

# System users
for user in cafebox cafebox-admin; do
    if id "$user" &>/dev/null; then
        ok "user '$user' exists: $(id "$user")"
    else
        fail "user '$user' does NOT exist"
    fi
done

# First-boot state
FLAG_FILE="/var/lib/cafebox/first-boot-done"
PASSWORD_FILE="/run/cafebox/initial-password"
STATUS_JSON="/run/cafebox/portal-status.json"

echo
if [ -f "$FLAG_FILE" ]; then
    ok "first-boot flag present: $FLAG_FILE"
else
    fail "first-boot flag MISSING: $FLAG_FILE (first-boot.sh did not complete)"
fi

if [ -d /run/cafebox ]; then
    ok "/run/cafebox directory exists"
    ls -la /run/cafebox/ 2>/dev/null || true
else
    fail "/run/cafebox directory MISSING"
fi

if [ -f "$PASSWORD_FILE" ]; then
    ok "initial password file present: $PASSWORD_FILE"
    printf '  password: %s\n' "$(maybe_redact "$(cat "$PASSWORD_FILE" 2>/dev/null)")"
else
    fail "initial password file MISSING: $PASSWORD_FILE"
fi

if [ -f "$STATUS_JSON" ]; then
    ok "portal-status.json present: $STATUS_JSON"
    printf '  contents: '
    cat "$STATUS_JSON" 2>/dev/null
    echo
else
    fail "portal-status.json MISSING: $STATUS_JSON"
fi

# Storage directories
echo
STORAGE_BASE="/srv/cafebox"
for dir in "$STORAGE_BASE" "$STORAGE_BASE/conduit" "$STORAGE_BASE/calibre" "$STORAGE_BASE/kiwix" "$STORAGE_BASE/navidrome"; do
    if [ -d "$dir" ]; then
        ok "directory exists: $dir (owner: $(stat -c '%U:%G' "$dir" 2>/dev/null || echo unknown))"
    else
        fail "directory MISSING: $dir"
    fi
done

# Portal web root
echo
PORTAL_ROOT="/var/www/cafebox/portal"
if [ -d "$PORTAL_ROOT" ]; then
    ok "portal root exists: $PORTAL_ROOT"
    if [ -f "$PORTAL_ROOT/index.html" ]; then
        ok "index.html present ($(wc -c < "$PORTAL_ROOT/index.html") bytes)"
    else
        fail "index.html MISSING from $PORTAL_ROOT"
    fi
else
    fail "portal root MISSING: $PORTAL_ROOT"
fi

# ============================= Section 8 ====================================
hdr "8. Listening Ports"

printf '  Ports 22 (SSH), 53 (DNS), 67 (DHCP), 80 (HTTP), 8000 (Admin):\n'
ss -tlnp 'sport = :22 or sport = :53 or sport = :67 or sport = :80 or sport = :8000' 2>/dev/null || warn "ss command failed"

# ============================= Section 9 ====================================
hdr "9. Service Journals (last 30 lines each)"

for svc in cafebox-first-boot hostapd dnsmasq nginx; do
    echo
    printf '  --- %s ---\n' "$svc"
    journalctl -u "$svc" --no-pager -n 30 2>/dev/null || warn "could not read $svc journal"
done

echo
printf '  --- Failed units ---\n'
systemctl --failed --no-pager 2>/dev/null || true

# ============================= Section 10 ===================================
hdr "10. Disk and Memory"

printf '  Filesystem usage:\n'
df -h 2>/dev/null || warn "df not available"

echo
printf '  Memory:\n'
free -h 2>/dev/null || warn "free not available"

# ============================= End ==========================================
hdr "End of diagnostics"
printf '  Log written to: %s\n' "${OUTPUT}"
printf '  Pull the SD card and read this file from the FAT32 boot partition.\n'
