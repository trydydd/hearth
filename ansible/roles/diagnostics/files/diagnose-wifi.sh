#!/usr/bin/env bash
# diagnose-wifi.sh — collect diagnostic information for the CafeBox WiFi
# access point (hostapd broadcast issue).
#
# Deployed to /usr/local/share/cafebox/diag/ on the target host by the
# diagnostics Ansible role (development only by default).
#
# Run on the Pi as root when the WiFi network is never broadcast:
#
#   sudo /usr/local/share/cafebox/diag/diagnose-wifi.sh
#
# The script walks the full AP bringup chain:
#   rfkill → interface present → firmware → IP address → regulatory domain
#   → hostapd (config + service + journal) → dnsmasq (config + service)
#
# It prints a clearly labelled report; share the full output when filing
# an issue.

set -euo pipefail

IFACE="${1:-wlan0}"

hr()  { printf '\n%s\n' "──────────────────────────────────────────────────────────────────"; }
hdr() { hr; printf '  %s\n' "$1"; hr; }
ok()  { printf '  [OK]   %s\n' "$1"; }
warn(){ printf '  [WARN] %s\n' "$1"; }
fail(){ printf '  [FAIL] %s\n' "$1"; }

hdr "CafeBox WiFi diagnostics — interface: ${IFACE}"
printf '  Run as: %s   Date: %s\n' "$(id -un)" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf '  Kernel:  %s\n' "$(uname -r)"
printf '  Machine: %s\n' "$(uname -m)"

# ---------------------------------------------------------------------------
hdr "1. rfkill status"
# ---------------------------------------------------------------------------
if command -v rfkill &>/dev/null; then
    rfkill list all || true
    echo
    # Soft-block: hostapd cannot bring up the AP
    if rfkill list all 2>/dev/null | grep -qA1 "Wireless LAN" | grep -q "Soft blocked: yes"; then
        fail "WiFi is SOFT-BLOCKED — run: rfkill unblock wifi"
    else
        ok "WiFi soft-block: no"
    fi
    # Hard-block: physical switch / hardware issue
    if rfkill list all 2>/dev/null | grep -qA2 "Wireless LAN" | grep -q "Hard blocked: yes"; then
        fail "WiFi is HARD-BLOCKED — check physical switch or wl_on_gpio in /boot/config.txt"
    else
        ok "WiFi hard-block: no"
    fi
else
    warn "rfkill command not found — cannot check radio block status"
fi

# ---------------------------------------------------------------------------
hdr "2. WiFi interface presence"
# ---------------------------------------------------------------------------
if ip link show "${IFACE}" &>/dev/null; then
    ok "interface ${IFACE} exists"
    ip link show "${IFACE}"
else
    fail "interface ${IFACE} does NOT exist"
    printf '\n  All available interfaces:\n'
    ip link show || true
    printf '\n  Wireless interfaces detected by iw:\n'
    if command -v iw &>/dev/null; then
        iw dev || true
    else
        warn "iw not installed"
    fi
    printf '\n  If no wireless interface appears, check:\n'
    printf '    - Firmware loaded (section 3)\n'
    printf '    - rfkill blocks (section 1)\n'
    printf '    - country code set in /boot/config.txt or /boot/firmware/config.txt\n'
fi

# ---------------------------------------------------------------------------
hdr "3. Wireless firmware and kernel modules"
# ---------------------------------------------------------------------------
printf '  Loaded brcm/cypress modules:\n'
lsmod | grep -E 'brcm|cypress|cfg80211|mac80211' || warn "no brcmfmac/cfg80211 modules loaded"
echo
printf '  dmesg (brcmfmac / firmware messages — last 30 lines):\n'
dmesg | grep -iE 'brcmfmac|firmware|wlan' | tail -30 || warn "no brcmfmac messages in dmesg"
echo
# Firmware files
FW_DIRS=(/lib/firmware/brcm /usr/lib/firmware/brcm)
for d in "${FW_DIRS[@]}"; do
    if [ -d "$d" ]; then
        ok "firmware directory found: $d"
        ls "$d" | grep -i "brcm" | head -10 || true
    fi
done

# ---------------------------------------------------------------------------
hdr "4. Interface IP address and mode"
# ---------------------------------------------------------------------------
if ip addr show "${IFACE}" &>/dev/null; then
    ip addr show "${IFACE}"
    echo
    # Expected AP IP is 10.0.0.1 (cafe.yaml box.ip default)
    if ip addr show "${IFACE}" 2>/dev/null | grep -q "10\.0\.0\.1"; then
        ok "AP IP address (10.0.0.1) is assigned to ${IFACE}"
    else
        warn "AP IP address (10.0.0.1) not found on ${IFACE}"
        warn "Expected: ip addr add 10.0.0.1/24 dev ${IFACE}"
        warn "This means no DHCP leases can be served even if hostapd starts"
    fi
    echo
    if command -v iw &>/dev/null; then
        printf '  iw dev %s info:\n' "${IFACE}"
        iw dev "${IFACE}" info 2>/dev/null || warn "could not query ${IFACE} via iw"
        echo
        IW_TYPE="$(iw dev "${IFACE}" info 2>/dev/null | awk '/type/{print $2}' || true)"
        if [ "${IW_TYPE}" = "AP" ]; then
            ok "${IFACE} is in AP mode"
        elif [ -n "${IW_TYPE}" ]; then
            warn "${IFACE} is in ${IW_TYPE} mode (expected AP)"
            warn "hostapd should set this automatically; if hostapd is not running the mode stays managed"
        else
            warn "could not determine interface mode"
        fi
    else
        warn "iw not installed — cannot check interface mode"
    fi
else
    warn "interface ${IFACE} not found — skipping IP/mode checks"
fi

# ---------------------------------------------------------------------------
hdr "5. Regulatory domain (country code)"
# ---------------------------------------------------------------------------
if command -v iw &>/dev/null; then
    printf '  Current regulatory domain:\n'
    iw reg get || warn "could not query regulatory domain"
    echo
    REG="$(iw reg get 2>/dev/null | awk '/country/{print $2}' | head -1 | tr -d : || true)"
    if [ "${REG}" = "00" ] || [ -z "${REG}" ]; then
        warn "Regulatory domain is '${REG:-unset}' (world/default)"
        warn "The Pi Zero 2 W requires a country code to operate on most channels."
        warn "Fix options:"
        warn "  1. Add 'country_code=GB' (or your country) to /etc/hostapd/hostapd.conf"
        warn "     and set ieee80211d=1 in the same file."
        warn "  2. Or set 'REGDOMAIN=GB' in /etc/default/crda (if crda is installed)."
        warn "  3. Or add 'cfg80211.ieee80211_regdom=GB' to /boot/cmdline.txt."
        warn "  Without a valid country code, transmission may be blocked by the kernel."
    else
        ok "Regulatory domain: ${REG}"
    fi
else
    warn "iw not installed — cannot check regulatory domain"
fi

# ---------------------------------------------------------------------------
hdr "6. hostapd service"
# ---------------------------------------------------------------------------
printf '  systemctl status hostapd:\n'
systemctl status hostapd --no-pager --full 2>&1 || true
echo

# Masked check — Debian/Raspbian masks hostapd by default
if systemctl is-enabled hostapd 2>&1 | grep -q "masked"; then
    fail "hostapd service is MASKED"
    fail "Fix: sudo systemctl unmask hostapd && sudo systemctl enable hostapd && sudo systemctl start hostapd"
elif systemctl is-enabled hostapd 2>/dev/null | grep -q "enabled"; then
    ok "hostapd is enabled"
else
    warn "hostapd is NOT enabled ($(systemctl is-enabled hostapd 2>/dev/null || echo unknown))"
fi

if systemctl is-active --quiet hostapd 2>/dev/null; then
    ok "hostapd is RUNNING"
else
    fail "hostapd is NOT running"
fi

# ---------------------------------------------------------------------------
hdr "7. hostapd journal (last 50 lines)"
# ---------------------------------------------------------------------------
journalctl -u hostapd --no-pager -n 50 2>/dev/null || warn "could not read hostapd journal"

# ---------------------------------------------------------------------------
hdr "8. hostapd configuration file"
# ---------------------------------------------------------------------------
HOSTAPD_CONF="/etc/hostapd/hostapd.conf"
HOSTAPD_DEFAULT="/etc/default/hostapd"

if [ -f "${HOSTAPD_CONF}" ]; then
    ok "hostapd config present: ${HOSTAPD_CONF}"
    printf '\n  Contents:\n'
    # Mask any passphrase to avoid leaking it in issue reports
    sed 's/\(wpa_passphrase\s*=\s*\).*/\1<REDACTED>/' "${HOSTAPD_CONF}"
    echo
    # Key value checks
    CONF_IFACE="$(grep -E '^interface=' "${HOSTAPD_CONF}" | cut -d= -f2 | tr -d ' ' || true)"
    if [ "${CONF_IFACE}" = "${IFACE}" ]; then
        ok "hostapd interface matches expected (${IFACE})"
    else
        warn "hostapd interface is '${CONF_IFACE}', expected '${IFACE}'"
        warn "Fix: update 'interface=' in ${HOSTAPD_CONF}"
    fi
else
    fail "hostapd config MISSING: ${HOSTAPD_CONF}"
    fail "Fix: re-provision with: ansible-playbook -i inventory/production site.yml"
fi

if [ -f "${HOSTAPD_DEFAULT}" ]; then
    printf '\n  %s:\n' "${HOSTAPD_DEFAULT}"
    cat "${HOSTAPD_DEFAULT}"
    # Raspbian/Ubuntu: DAEMON_CONF must point to the config file
    if grep -qE "^DAEMON_CONF" "${HOSTAPD_DEFAULT}"; then
        DAEMON_CONF="$(grep -E '^DAEMON_CONF' "${HOSTAPD_DEFAULT}" | cut -d= -f2 | tr -d '"' | tr -d ' ' || true)"
        if [ "${DAEMON_CONF}" = "${HOSTAPD_CONF}" ]; then
            ok "DAEMON_CONF points to ${HOSTAPD_CONF}"
        elif [ -z "${DAEMON_CONF}" ]; then
            warn "DAEMON_CONF is empty in ${HOSTAPD_DEFAULT}"
            warn "Fix: set DAEMON_CONF=\"${HOSTAPD_CONF}\" in ${HOSTAPD_DEFAULT}"
        else
            warn "DAEMON_CONF points to '${DAEMON_CONF}', expected '${HOSTAPD_CONF}'"
        fi
    else
        warn "DAEMON_CONF not set in ${HOSTAPD_DEFAULT}"
        warn "On Debian/Raspbian this may prevent hostapd from reading its config."
        warn "Fix: add DAEMON_CONF=\"${HOSTAPD_CONF}\" to ${HOSTAPD_DEFAULT}"
    fi
fi

# ---------------------------------------------------------------------------
hdr "9. dnsmasq service"
# ---------------------------------------------------------------------------
printf '  systemctl status dnsmasq:\n'
systemctl status dnsmasq --no-pager --full 2>&1 || true
echo

if systemctl is-active --quiet dnsmasq 2>/dev/null; then
    ok "dnsmasq is RUNNING"
else
    fail "dnsmasq is NOT running"
fi

# ---------------------------------------------------------------------------
hdr "10. dnsmasq configuration file"
# ---------------------------------------------------------------------------
DNSMASQ_CONF="/etc/dnsmasq.d/cafebox.conf"

if [ -f "${DNSMASQ_CONF}" ]; then
    ok "dnsmasq config present: ${DNSMASQ_CONF}"
    printf '\n  Contents:\n'
    cat "${DNSMASQ_CONF}"
else
    fail "dnsmasq config MISSING: ${DNSMASQ_CONF}"
    fail "Fix: re-provision with: ansible-playbook -i inventory/production site.yml"
fi

# ---------------------------------------------------------------------------
hdr "11. dnsmasq journal (last 30 lines)"
# ---------------------------------------------------------------------------
journalctl -u dnsmasq --no-pager -n 30 2>/dev/null || warn "could not read dnsmasq journal"

# ---------------------------------------------------------------------------
hdr "12. Network interfaces summary"
# ---------------------------------------------------------------------------
ip addr show || ip link show || warn "ip command not available"

# ---------------------------------------------------------------------------
hdr "13. Listening ports (DNS :53, DHCP :67)"
# ---------------------------------------------------------------------------
ss -ulnp 'sport = :53 or sport = :67' 2>/dev/null || true
ss -tlnp 'sport = :53' 2>/dev/null || true

# ---------------------------------------------------------------------------
hdr "14. Boot config (WiFi / Pi Zero 2 W specific)"
# ---------------------------------------------------------------------------
# RPi OS Bookworm and later stores config under /boot/firmware/; older images use /boot/
for BOOT_CFG in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "${BOOT_CFG}" ]; then
        ok "Found: ${BOOT_CFG}"
        printf '\n  WiFi / DTPARAM / DTOVERLAY / COUNTRY lines:\n'
        grep -iE 'dtoverlay|dtparam.*wifi|country|disable_wifi|wifioff|bcm2710' "${BOOT_CFG}" || warn "no relevant wifi lines found in ${BOOT_CFG}"
        echo
        # disable_wifi is a known way to kill the Pi Zero 2 W radio
        if grep -qi "disable_wifi" "${BOOT_CFG}"; then
            fail "disable_wifi found in ${BOOT_CFG} — WiFi is disabled at firmware level"
            fail "Fix: remove or comment out the 'dtoverlay=disable-wifi' line and reboot"
        fi
    fi
done
for CMDLINE in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -f "${CMDLINE}" ]; then
        ok "Found: ${CMDLINE}"
        cat "${CMDLINE}"
        echo
    fi
done

# ---------------------------------------------------------------------------
hdr "15. systemd-networkd / NetworkManager — potential conflict with hostapd"
# ---------------------------------------------------------------------------
printf '  Active network managers:\n'
for svc in NetworkManager systemd-networkd wpa_supplicant; do
    STATE="$(systemctl is-active "${svc}" 2>/dev/null || echo inactive)"
    if [ "${STATE}" = "active" ]; then
        warn "${svc} is ACTIVE — it may conflict with hostapd managing ${IFACE}"
        warn "If ${svc} tries to manage ${IFACE} it will race with hostapd."
    else
        ok "${svc}: ${STATE}"
    fi
done
echo
# wpa_supplicant on the AP interface is a common conflict
if pgrep -f "wpa_supplicant.*${IFACE}" 2>/dev/null | grep -q .; then
    fail "wpa_supplicant is running on ${IFACE} — this WILL prevent hostapd from claiming the interface"
    fail "Fix: stop wpa_supplicant on ${IFACE} before starting hostapd"
    fail "     systemctl stop wpa_supplicant@${IFACE}"
else
    ok "wpa_supplicant is not running on ${IFACE}"
fi

# ---------------------------------------------------------------------------
hdr "16. USB OTG gadget (SSH over USB cable)"
# ---------------------------------------------------------------------------
# If the WiFi AP is broken, SSH over USB is the primary fallback for accessing
# the Pi.  This section shows whether the USB gadget is configured correctly.

printf '  Kernel modules:\n'
if lsmod 2>/dev/null | grep -q "g_ether\|usb_f_ecm\|usb_f_rndis"; then
    ok "USB Ethernet gadget module loaded"
    lsmod | grep -E 'g_ether|usb_f_ecm|usb_f_rndis|dwc2' || true
elif lsmod 2>/dev/null | grep -q "dwc2"; then
    warn "dwc2 loaded but g_ether not yet loaded (gadget driver not bound)"
    warn "This means usb0 will not appear until g_ether is loaded."
    warn "Check cmdline.txt for modules-load=dwc2,g_ether"
else
    warn "Neither dwc2 nor g_ether modules are loaded"
    warn "USB OTG gadget is not active — SSH over USB cable is not available"
fi
echo

printf '  usb0 interface:\n'
if ip link show usb0 &>/dev/null; then
    ok "usb0 interface exists"
    ip addr show usb0
    echo
    USB_IP="$(ip addr show usb0 2>/dev/null | awk '/inet /{print $2}' | head -1 || true)"
    if [ -n "${USB_IP}" ]; then
        ok "usb0 has IP address: ${USB_IP}"
        printf '  Connect from the host with:\n'
        printf '    ssh <user>@%s\n' "${USB_IP%%/*}"
    else
        warn "usb0 has no IP address — check dhcpcd.conf for usb0 static config"
    fi
else
    warn "usb0 interface does NOT exist"
    warn "Either no USB cable is connected, or the gadget module is not loaded"
fi
echo

printf '  SSH service:\n'
if systemctl is-active --quiet ssh 2>/dev/null; then
    ok "ssh service is RUNNING"
elif systemctl is-active --quiet sshd 2>/dev/null; then
    ok "sshd service is RUNNING"
else
    fail "SSH service is NOT running"
    fail "Fix: sudo systemctl enable --now ssh"
fi
echo

printf '  USB gadget boot config:\n'
for BOOT_CFG in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "${BOOT_CFG}" ]; then
        if grep -q "^dtoverlay=dwc2" "${BOOT_CFG}"; then
            ok "dtoverlay=dwc2 found in ${BOOT_CFG}"
        else
            warn "dtoverlay=dwc2 NOT found in ${BOOT_CFG}"
            warn "Fix: add 'dtoverlay=dwc2' to ${BOOT_CFG} and reboot"
        fi
        break
    fi
done
for CMDLINE in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -f "${CMDLINE}" ]; then
        if grep -q "modules-load=dwc2,g_ether" "${CMDLINE}"; then
            ok "modules-load=dwc2,g_ether found in ${CMDLINE}"
        else
            warn "modules-load=dwc2,g_ether NOT found in ${CMDLINE}"
            warn "Fix: append 'modules-load=dwc2,g_ether' to ${CMDLINE} and reboot"
        fi
        break
    fi
done

# ---------------------------------------------------------------------------
hdr "Done"
# ---------------------------------------------------------------------------
printf '  Paste the full output above into the GitHub issue.\n'
printf '  Tip: save to a file with:\n'
printf '    sudo %s 2>&1 | tee /tmp/cafebox-wifi-diag.txt\n' "$0"
