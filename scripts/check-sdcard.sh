#!/usr/bin/env bash
# scripts/check-sdcard.sh — Hearth SD card diagnostic collector
#
# Run on your laptop with a Hearth (or base RPi OS) SD card mounted.
# Collects everything needed to diagnose WiFi, services, and first-boot issues.
# Paste the full output back to Claude.
#
# Usage:
#   sudo ./scripts/check-sdcard.sh                    # auto-detect mounts
#   sudo ./scripts/check-sdcard.sh /mnt/rootfs /mnt/bootfs  # explicit paths
#
# Why sudo: several key files (wpa_supplicant.conf, admin.env) are mode 0600.

set -uo pipefail

# ---------------------------------------------------------------------------
# Colour / formatting helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YEL='\033[0;33m'; GRN='\033[0;32m'; RST='\033[0m'
BOLD='\033[1m'
ok()   { printf "${GRN}  [OK]${RST}   %s\n" "$1"; }
warn() { printf "${YEL}  [WARN]${RST} %s\n" "$1"; }
fail() { printf "${RED}  [FAIL]${RST} %s\n" "$1"; FAILURES=$((FAILURES+1)); }
hdr()  { printf "\n${BOLD}=== %s ===${RST}\n" "$1"; }
sub()  { printf "\n${BOLD}--- %s ---${RST}\n" "$1"; }
show() {
    local label="$1" path="$2"
    if [ -f "$path" ]; then
        printf "\n  >> %s (%s)\n" "$label" "$path"
        sed 's/^/     /' "$path"
    elif [ -d "$path" ]; then
        printf "\n  >> %s (%s)\n" "$label" "$path"
        ls -la "$path" 2>&1 | sed 's/^/     /'
    else
        printf "  [missing] %s (%s)\n" "$label" "$path"
    fi
}
check_file() {
    local label="$1" path="$2"
    [ -f "$path" ] && ok "$label present" || fail "$label MISSING at $path"
}
check_link() {
    local label="$1" path="$2"
    [ -L "$path" ] && ok "$label" || fail "$label — symlink missing at $path"
}

FAILURES=0

# ---------------------------------------------------------------------------
# Privilege check — used to read 0600 files (wpa_supplicant.conf, admin.env)
# ---------------------------------------------------------------------------
READ_CMD="cat"
if [ "$(id -u)" -ne 0 ]; then
    if sudo -n true 2>/dev/null; then
        READ_CMD="sudo cat"
        echo "(running as non-root; using sudo for protected files)"
    else
        echo "(running as non-root without passwordless sudo — protected files may show as missing)"
    fi
fi

# ---------------------------------------------------------------------------
# Locate mount points
# ---------------------------------------------------------------------------
ROOT_MNT="${1:-}"
BOOT_MNT="${2:-}"

auto_detect_mounts() {
    # Look for mounted partitions with the Pi OS layout:
    # rootfs: ext4 with /etc/os-release and /opt/hearth or /etc/hostapd
    # bootfs: vfat with cmdline.txt
    while IFS= read -r line; do
        local dev mnt fstype
        dev=$(echo "$line" | awk '{print $1}')
        mnt=$(echo "$line" | awk '{print $2}')
        fstype=$(echo "$line" | awk '{print $3}')

        if [ "$fstype" = "ext4" ] && [ -f "$mnt/etc/os-release" ] && [ -d "$mnt/etc/systemd" ]; then
            ROOT_MNT="$mnt"
        fi
        if [ "$fstype" = "vfat" ] && [ -f "$mnt/cmdline.txt" ]; then
            BOOT_MNT="$mnt"
        fi
    done < <(grep -E "ext4|vfat" /proc/mounts 2>/dev/null || true)
}

if [ -z "$ROOT_MNT" ] || [ -z "$BOOT_MNT" ]; then
    auto_detect_mounts
fi

# Fallback to common paths
[ -z "$ROOT_MNT" ] && ROOT_MNT="/media/$(logname 2>/dev/null || echo slider)/rootfs"
[ -z "$BOOT_MNT" ] && BOOT_MNT="/media/$(logname 2>/dev/null || echo slider)/bootfs"

printf "\n${BOLD}Hearth SD Card Diagnostic Report${RST}\n"
printf "Generated: %s\n" "$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
printf "Root mount: %s\n" "$ROOT_MNT"
printf "Boot mount: %s\n" "$BOOT_MNT"

if [ ! -d "$ROOT_MNT/etc" ]; then
    echo ""
    echo "ERROR: rootfs not found at $ROOT_MNT"
    echo "Usage: sudo $0 /path/to/rootfs /path/to/bootfs"
    exit 1
fi
if [ ! -f "$BOOT_MNT/cmdline.txt" ]; then
    echo ""
    echo "ERROR: bootfs not found at $BOOT_MNT (no cmdline.txt)"
    echo "Usage: sudo $0 /path/to/rootfs /path/to/bootfs"
    exit 1
fi

# ---------------------------------------------------------------------------
# BOOT PARTITION
# ---------------------------------------------------------------------------
hdr "BOOT PARTITION"

sub "cmdline.txt"
cat "$BOOT_MNT/cmdline.txt" 2>/dev/null | sed 's/^/  /'
echo ""

# Key boot parameters
CMDLINE=$(cat "$BOOT_MNT/cmdline.txt" 2>/dev/null || echo "")
if echo "$CMDLINE" | grep -q "cfg80211.ieee80211_regdom="; then
    REGDOM=$(echo "$CMDLINE" | grep -o 'cfg80211.ieee80211_regdom=[^ ]*')
    ok "Regulatory domain: $REGDOM"
else
    fail "cfg80211.ieee80211_regdom= ABSENT from cmdline.txt — WiFi AP will not broadcast on Trixie"
fi

if echo "$CMDLINE" | grep -q "modules-load=dwc2,g_ether"; then
    ok "USB OTG: modules-load=dwc2,g_ether present"
else
    warn "USB OTG: modules-load=dwc2,g_ether absent (expected if usb_ssh.enabled: false)"
fi

sub "config.txt (WiFi / USB OTG relevant)"
grep -E "^(dtoverlay|dtparam|gpu_mem|arm_64bit|\[)" "$BOOT_MNT/config.txt" 2>/dev/null | sed 's/^/  /' || echo "  (config.txt not found or no matching lines)"

sub "Boot partition files"
for f in userconf.txt ssh user-data network-config firstrun.sh hearth-diagnostics.log; do
    if [ -f "$BOOT_MNT/$f" ]; then
        SIZE=$(wc -c < "$BOOT_MNT/$f")
        MTIME=$(stat -c '%y' "$BOOT_MNT/$f" 2>/dev/null | cut -d'.' -f1)
        ok "$f present (${SIZE} bytes, modified $MTIME)"
    else
        echo "  [absent]  $f"
    fi
done

if [ -f "$BOOT_MNT/hearth-diagnostics.log" ]; then
    sub "hearth-diagnostics.log (last 80 lines)"
    tail -80 "$BOOT_MNT/hearth-diagnostics.log" | sed 's/^/  /'
fi

# ---------------------------------------------------------------------------
# OS / IMAGE IDENTITY
# ---------------------------------------------------------------------------
hdr "OS IDENTITY"
cat "$ROOT_MNT/etc/os-release" 2>/dev/null | sed 's/^/  /' || echo "  (os-release not found)"
echo ""
if [ -f "$ROOT_MNT/etc/rpi-issue" ]; then
    echo "  rpi-issue: $(cat "$ROOT_MNT/etc/rpi-issue" 2>/dev/null)"
fi
PKG_VER=$(grep -r "raspberrypi-sys-mods" "$ROOT_MNT/var/lib/dpkg/status" 2>/dev/null | grep "^Version:" | head -1 || echo "")
[ -n "$PKG_VER" ] && echo "  raspberrypi-sys-mods: $PKG_VER" || echo "  raspberrypi-sys-mods: not found in dpkg/status"

# ---------------------------------------------------------------------------
# WIFI / HOSTAPD
# ---------------------------------------------------------------------------
hdr "WIFI — HOSTAPD"

show "hostapd.conf" "$ROOT_MNT/etc/hostapd/hostapd.conf"
show "/etc/default/hostapd" "$ROOT_MNT/etc/default/hostapd"

sub "Checks"
check_file "hostapd.conf" "$ROOT_MNT/etc/hostapd/hostapd.conf"

if grep -q "^DAEMON_CONF=" "$ROOT_MNT/etc/default/hostapd" 2>/dev/null; then
    DCVAL=$(grep "^DAEMON_CONF=" "$ROOT_MNT/etc/default/hostapd" | cut -d= -f2)
    ok "DAEMON_CONF=$DCVAL"
else
    fail "DAEMON_CONF not set in /etc/default/hostapd — hostapd will start without config"
fi

check_link "hostapd.service enabled" "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/hostapd.service"
check_file "hostapd drop-in (wlan-wait)" "$ROOT_MNT/etc/systemd/system/hostapd.service.d/hearth-wlan-wait.conf"

if [ -f "$ROOT_MNT/etc/systemd/system/hostapd.service.d/hearth-wlan-wait.conf" ]; then
    if grep -q "rfkill unblock wifi" "$ROOT_MNT/etc/systemd/system/hostapd.service.d/hearth-wlan-wait.conf" 2>/dev/null; then
        ok "rfkill unblock wifi in hostapd drop-in"
    else
        fail "rfkill unblock wifi ABSENT from hostapd drop-in"
    fi
    if grep -q "BindsTo=sys-subsystem-net-devices-wlan0.device" "$ROOT_MNT/etc/systemd/system/hostapd.service.d/hearth-wlan-wait.conf" 2>/dev/null; then
        ok "BindsTo=wlan0.device in hostapd drop-in"
    else
        warn "BindsTo=wlan0.device not found in hostapd drop-in"
    fi
fi

# ---------------------------------------------------------------------------
# WIFI — REGULATORY DOMAIN
# ---------------------------------------------------------------------------
hdr "WIFI — REGULATORY DOMAIN"

sub "wpa_supplicant.conf"
if [ -f "$ROOT_MNT/etc/wpa_supplicant/wpa_supplicant.conf" ]; then
    $READ_CMD "$ROOT_MNT/etc/wpa_supplicant/wpa_supplicant.conf" 2>/dev/null | sed 's/^/  /' || echo "  (permission denied — run as root to read)"
    if grep -q "^country=" "$ROOT_MNT/etc/wpa_supplicant/wpa_supplicant.conf" 2>/dev/null; then
        CTRY=$(grep "^country=" "$ROOT_MNT/etc/wpa_supplicant/wpa_supplicant.conf")
        ok "wpa_supplicant.conf: $CTRY (legacy fallback)"
    else
        warn "country= absent from wpa_supplicant.conf (OK on Trixie — cmdline.txt is primary)"
    fi
else
    warn "wpa_supplicant.conf not found"
fi

if [ -f "$ROOT_MNT/etc/default/crda" ]; then
    CRDAVAL=$(grep "^REGDOMAIN=" "$ROOT_MNT/etc/default/crda" 2>/dev/null || echo "(not set)")
    ok "/etc/default/crda: $CRDAVAL"
else
    warn "/etc/default/crda not found"
fi

# ---------------------------------------------------------------------------
# WIFI — DNSMASQ
# ---------------------------------------------------------------------------
hdr "WIFI — DNSMASQ"

check_file "dnsmasq hearth.conf" "$ROOT_MNT/etc/dnsmasq.d/hearth.conf"
check_link "dnsmasq.service enabled" "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/dnsmasq.service"
check_file "dnsmasq drop-in" "$ROOT_MNT/etc/systemd/system/dnsmasq.service.d/hearth-wlan-wait.conf"
show "dnsmasq hearth.conf" "$ROOT_MNT/etc/dnsmasq.d/hearth.conf"

# ---------------------------------------------------------------------------
# NETWORK — dhcpcd / NetworkManager
# ---------------------------------------------------------------------------
hdr "NETWORK"

sub "dhcpcd.conf (wlan0 / usb0 blocks)"
if [ -f "$ROOT_MNT/etc/dhcpcd.conf" ]; then
    grep -A5 "ANSIBLE MANAGED\|interface wlan0\|interface usb0" "$ROOT_MNT/etc/dhcpcd.conf" 2>/dev/null | sed 's/^/  /' || echo "  (no relevant blocks found)"
else
    echo "  /etc/dhcpcd.conf not found"
fi

sub "NetworkManager — hearth-wifi.conf"
if [ -f "$ROOT_MNT/etc/NetworkManager/conf.d/hearth-wifi.conf" ]; then
    cat "$ROOT_MNT/etc/NetworkManager/conf.d/hearth-wifi.conf" | sed 's/^/  /'
    ok "NetworkManager unmanaged config present"
else
    warn "hearth-wifi.conf not found — NetworkManager may claim wlan0"
fi

# ---------------------------------------------------------------------------
# SYSTEMD SERVICES
# ---------------------------------------------------------------------------
hdr "SYSTEMD — ENABLED SERVICES"

sub "multi-user.target.wants"
ls "$ROOT_MNT/etc/systemd/system/multi-user.target.wants/" 2>/dev/null | sed 's/^/  /' || echo "  (directory not found)"

EXPECTED_SERVICES=(
    "hostapd.service"
    "dnsmasq.service"
    "nginx.service"
    "hearth-admin-backend.service"
    "hearth-first-boot.service"
    "hearth-boot-dump.service"
)
echo ""
for svc in "${EXPECTED_SERVICES[@]}"; do
    LINK="$ROOT_MNT/etc/systemd/system/multi-user.target.wants/$svc"
    if [ -L "$LINK" ]; then
        TARGET=$(readlink "$LINK" 2>/dev/null || echo "?")
        ACTUAL="${ROOT_MNT}${TARGET}"
        if [ -f "$ACTUAL" ]; then
            ok "$svc enabled (unit exists)"
        else
            fail "$svc enabled but unit file MISSING at $TARGET"
        fi
    else
        fail "$svc NOT enabled"
    fi
done

sub "hearth-boot-dump.service unit"
show "hearth-boot-dump.service" "$ROOT_MNT/etc/systemd/system/hearth-boot-dump.service"

sub "hearth-first-boot.service unit"
show "hearth-first-boot.service" "$ROOT_MNT/etc/systemd/system/hearth-first-boot.service"

sub "hearth-admin-backend.service unit"
show "hearth-admin-backend.service" "$ROOT_MNT/etc/systemd/system/hearth-admin-backend.service"

# ---------------------------------------------------------------------------
# HEARTH SERVICES — FILES ON DISK
# ---------------------------------------------------------------------------
hdr "HEARTH — DEPLOYED FILES"

sub "/opt/hearth layout"
if [ -d "$ROOT_MNT/opt/hearth" ]; then
    ok "/opt/hearth exists"
    find "$ROOT_MNT/opt/hearth" -maxdepth 3 -printf '  %P\n' 2>/dev/null | head -40 || true
else
    fail "/opt/hearth MISSING — admin backend not deployed"
fi

sub "/etc/hearth"
if [ -d "$ROOT_MNT/etc/hearth" ]; then
    ok "/etc/hearth exists"
    ls -la "$ROOT_MNT/etc/hearth/" 2>/dev/null | sed 's/^/  /'
else
    fail "/etc/hearth MISSING"
fi

sub "/usr/local/share/hearth/diag"
if [ -d "$ROOT_MNT/usr/local/share/hearth/diag" ]; then
    ok "diagnostics directory present"
    ls -la "$ROOT_MNT/usr/local/share/hearth/diag/" | sed 's/^/  /'
else
    fail "diagnostics directory MISSING at /usr/local/share/hearth/diag"
fi

sub "/usr/local/sbin/hearth-first-boot.sh"
check_file "hearth-first-boot.sh" "$ROOT_MNT/usr/local/sbin/hearth-first-boot.sh"

sub "/var/lib/hearth (first-boot state)"
if [ -d "$ROOT_MNT/var/lib/hearth" ]; then
    ok "/var/lib/hearth exists"
    ls -la "$ROOT_MNT/var/lib/hearth/" 2>/dev/null | sed 's/^/  /'
else
    warn "/var/lib/hearth not found (created at runtime)"
fi

sub "/var/www/hearth layout"
if [ -d "$ROOT_MNT/var/www/hearth" ]; then
    ok "/var/www/hearth exists"
    find "$ROOT_MNT/var/www/hearth" -maxdepth 2 -printf '  %P\n' 2>/dev/null | head -20 || true
else
    fail "/var/www/hearth MISSING"
fi

# ---------------------------------------------------------------------------
# NGINX
# ---------------------------------------------------------------------------
hdr "NGINX"
# nginx site may be named 'hearth' or 'hearth.conf' depending on role version
NGINX_SITE=""
for candidate in hearth.conf hearth; do
    if [ -f "$ROOT_MNT/etc/nginx/sites-available/$candidate" ]; then
        NGINX_SITE="$candidate"
        break
    fi
done
if [ -n "$NGINX_SITE" ]; then
    ok "nginx hearth site present (sites-available/$NGINX_SITE)"
else
    fail "nginx hearth site MISSING (checked hearth.conf and hearth)"
fi
if [ -L "$ROOT_MNT/etc/nginx/sites-enabled/${NGINX_SITE:-hearth.conf}" ]; then
    ok "nginx site enabled"
else
    fail "nginx site NOT enabled in sites-enabled"
fi
if [ -L "$ROOT_MNT/etc/nginx/sites-enabled/default" ]; then
    warn "default nginx site still enabled — should be removed"
else
    ok "default nginx site removed from sites-enabled"
fi
sub "nginx hearth site (location blocks)"
grep -E "^\s*(location|server_name|listen|root|return|proxy_pass)" \
    "$ROOT_MNT/etc/nginx/sites-available/${NGINX_SITE:-hearth.conf}" 2>/dev/null \
    | sed 's/^/  /' || echo "  (not found)"

# ---------------------------------------------------------------------------
# USB OTG SSH
# ---------------------------------------------------------------------------
hdr "USB OTG SSH"
if echo "$CMDLINE" | grep -q "modules-load=dwc2,g_ether"; then
    ok "USB OTG kernel modules in cmdline.txt"
    # Check config.txt for dtoverlay=dwc2
    if grep -qE "^dtoverlay=dwc2" "$BOOT_MNT/config.txt" 2>/dev/null; then
        ok "dtoverlay=dwc2 in config.txt"
    else
        fail "dtoverlay=dwc2 NOT in config.txt (USB OTG gadget won't load)"
    fi
    check_file "SSH enable file" "$BOOT_MNT/ssh"
else
    echo "  USB OTG SSH not configured (modules-load=dwc2,g_ether absent from cmdline.txt)"
fi

# ---------------------------------------------------------------------------
# PACKAGES — KEY DPKG VERSIONS
# ---------------------------------------------------------------------------
hdr "INSTALLED PACKAGES (key)"
DPKG_STATUS="$ROOT_MNT/var/lib/dpkg/status"
if [ ! -f "$DPKG_STATUS" ]; then
    echo "  (dpkg/status not found — cannot check packages)"
else
    for pkg in hostapd dnsmasq nginx python3 ansible raspberrypi-sys-mods raspi-config rfkill iw wpasupplicant network-manager dhcpcd5; do
        BLOCK=$(awk "/^Package: $pkg\$/{found=1} found{print} /^$/{found=0}" "$DPKG_STATUS" 2>/dev/null || true)
        VER=$(printf '%s' "$BLOCK" | grep "^Version:" | head -1 | awk '{print $2}' || true)
        STATUS=$(printf '%s' "$BLOCK" | grep "^Status:" | head -1 || true)
        if echo "$STATUS" | grep -q "installed" 2>/dev/null; then
            printf "  ${GRN}%-35s %s${RST}\n" "$pkg" "$VER"
        elif [ -n "$VER" ]; then
            printf "  ${YEL}%-35s %s (not fully installed)${RST}\n" "$pkg" "$VER"
        else
            printf "  %-35s %s\n" "$pkg" "(not installed)"
        fi
    done
fi

# ---------------------------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------------------------
hdr "SUMMARY"
if [ "$FAILURES" -eq 0 ]; then
    printf "${GRN}${BOLD}All checks passed.${RST} No obvious configuration problems found.\n"
else
    printf "${RED}${BOLD}%d check(s) failed${RST} — see [FAIL] lines above.\n" "$FAILURES"
fi
echo ""
exit 0
