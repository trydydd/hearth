#!/usr/bin/env bash
# scripts/build-image.sh — Build a flashable Hearth Raspberry Pi image
#
# Usage:
#   scripts/build-image.sh [--output <path>] [--work-dir <path>]
#
# Environment variables (override defaults):
#   HEARTH_CONFIG Path to hearth.yaml              (default: hearth.yaml)
#   OUTPUT_IMAGE  Destination .img.xz file         (default: image/hearth.img.xz)
#   WORK_DIR      Scratch directory for build artifacts (default: /tmp/hearth-build)
#   RPI_OS_URL    URL of the base Raspberry Pi OS Lite image
#   KEEP_WORK     Set to "1" to keep WORK_DIR after a successful build
#
# What this script does:
#   1. Downloads the latest Raspberry Pi OS Lite (64-bit) image.
#   2. Copies it to a raw working image so the original is never modified.
#   3. Mounts the image via a loop device and runs ansible/site.yml inside
#      a chroot, provisioning the image exactly as the Vagrantfile Ansible
#      provisioner would.
#   4. Validates the provisioned image configuration (WiFi AP + USB OTG SSH)
#      inside the container before capture — fails the build on any error.
#   5. Compresses the finished image to <output>.img.xz.
#
# Host architecture requirement:
#   This script must run on a native ARM64 (aarch64) host so that the chroot
#   executes ARM64 binaries directly — no cross-architecture emulation is used.
#   Suitable build hosts include:
#     - GitHub Actions runner: ubuntu-24.04-arm
#     - Raspberry Pi (any model running a 64-bit OS)
#     - AWS Graviton, Ampere Altra, or other ARM64 cloud instance
#     - Apple M-series Mac (inside a Linux VM or container)
#
# Required host tools (see image/README.md for installation instructions):
#   ansible  systemd-nspawn  xz  kpartx  losetup  parted  rsync  wget
#
# Estimated build time: 10–30 minutes on a native ARM64 host.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HEARTH_CONFIG="${HEARTH_CONFIG:-${REPO_ROOT}/hearth.yaml}"
OUTPUT_IMAGE="${OUTPUT_IMAGE:-${REPO_ROOT}/image/hearth.img.xz}"
WORK_DIR="${WORK_DIR:-/tmp/hearth-build}"
KEEP_WORK="${KEEP_WORK:-0}"

# Target image size.  6 GB gives ample headroom over the ~2 GB base image
# while still fitting on any 8 GB+ SD card.  Raspberry Pi OS expands the root
# filesystem to fill the SD card automatically on first boot, so there is no
# need to match the card size here.
IMAGE_SIZE="${IMAGE_SIZE:-6G}"

# Raspberry Pi OS Lite 64-bit — update URL to pin a specific release
RPI_OS_URL="${RPI_OS_URL:-https://downloads.raspberrypi.org/raspios_lite_arm64_latest}"

SCRIPT_NAME="$(basename "$0")"
LOG_PREFIX="[${SCRIPT_NAME}]"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "${LOG_PREFIX} $*"; }
die()  { echo "${LOG_PREFIX} ERROR: $*" >&2; exit 1; }
need() {
    for cmd in "$@"; do
        command -v "$cmd" >/dev/null 2>&1 || die "Required tool not found: $cmd. See image/README.md."
    done
}

_cleanup() {
    local exit_code=$?
    log "Cleaning up mount points..."
    # Unmount in reverse order; ignore errors during cleanup.
    # BOOT_MOUNT_DIR can be either /mnt/boot/firmware (Bookworm/Trixie and later)
    # or /mnt/boot (legacy), depending on what was detected at runtime.
    if [ -n "${BOOT_MOUNT_DIR:-}" ] && mountpoint -q "${BOOT_MOUNT_DIR}" 2>/dev/null; then
        umount "${BOOT_MOUNT_DIR}" 2>/dev/null || true
    fi
    if mountpoint -q "${MOUNT_DIR}" 2>/dev/null; then
        umount "${MOUNT_DIR}" 2>/dev/null || true
    fi
    if [ -n "${LOOP_DEV:-}" ]; then
        kpartx -d "${LOOP_DEV}" 2>/dev/null || true
        losetup -d "${LOOP_DEV}" 2>/dev/null || true
    fi
    if [ "${KEEP_WORK}" != "1" ] && [ $exit_code -eq 0 ]; then
        log "Removing work directory ${WORK_DIR}"
        rm -rf "${WORK_DIR}"
    else
        log "Work directory retained at ${WORK_DIR}"
    fi
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)   OUTPUT_IMAGE="$2"; shift 2 ;;
        --work-dir) WORK_DIR="$2";     shift 2 ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) die "Unknown argument: $1. Use --help for usage." ;;
    esac
done

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

# Enforce native ARM64 host — the chroot must execute ARM64 binaries directly
# without any QEMU cross-architecture emulation.
HOST_ARCH="$(uname -m)"
if [ "${HOST_ARCH}" != "aarch64" ]; then
    die "This script requires a native ARM64 (aarch64) host. \
Detected: ${HOST_ARCH}. \
Run on a Raspberry Pi, an ARM64 CI runner (ubuntu-24.04-arm), or an \
ARM64 cloud instance. Cross-architecture emulation via QEMU is intentionally \
not used — see image/README.md for details."
fi

need ansible systemd-nspawn xz kpartx losetup parted wget

if [ "$(id -u)" -ne 0 ]; then
    die "This script must be run as root (use sudo)."
fi

[ -f "${HEARTH_CONFIG}" ] || die "hearth.yaml not found at ${HEARTH_CONFIG}"

OUTPUT_DIR="$(dirname "${OUTPUT_IMAGE}")"
mkdir -p "${OUTPUT_DIR}" "${WORK_DIR}"

# Derived paths
RAW_IMAGE="${WORK_DIR}/raspios-lite.img"
WORK_IMAGE="${WORK_DIR}/hearth-work.img"
MOUNT_DIR="${WORK_DIR}/mnt"
LOOP_DEV=""
BOOT_MOUNT_DIR=""  # set after the root partition is mounted (modern vs legacy layout)

trap _cleanup EXIT

log "Build started"
log "  Host    : ${HOST_ARCH} (native — no emulation)"
log "  Config  : ${HEARTH_CONFIG}"
log "  Output  : ${OUTPUT_IMAGE}"
log "  WorkDir : ${WORK_DIR}"
log "  ImgSize : ${IMAGE_SIZE} (root partition; SD card is expanded to full size on first boot)"

# ---------------------------------------------------------------------------
# Step 1 — Download base image (skip if already present)
# ---------------------------------------------------------------------------
log "Step 1: Downloading Raspberry Pi OS Lite base image..."
if [ ! -f "${RAW_IMAGE}" ]; then
    DOWNLOAD_TARGET="${WORK_DIR}/raspios-lite.img.xz"
    wget --progress=dot:giga -O "${DOWNLOAD_TARGET}" "${RPI_OS_URL}"
    log "Decompressing base image..."
    xz -d "${DOWNLOAD_TARGET}"
    # wget saves the file with a Content-Disposition-derived name; rename to our target
    DOWNLOADED_IMG="$(ls "${WORK_DIR}"/*.img 2>/dev/null | head -1)"
    [ -n "${DOWNLOADED_IMG}" ] || die "Could not find downloaded .img file in ${WORK_DIR}"
    if [ "${DOWNLOADED_IMG}" != "${RAW_IMAGE}" ]; then
        mv "${DOWNLOADED_IMG}" "${RAW_IMAGE}"
    fi
    log "Base image saved to ${RAW_IMAGE}"
else
    log "Base image already present — skipping download."
fi

# ---------------------------------------------------------------------------
# Step 2 — Create a working copy
# ---------------------------------------------------------------------------
log "Step 2: Creating working copy..."
cp "${RAW_IMAGE}" "${WORK_IMAGE}"
# Extend partition/filesystem to give headroom for provisioned packages.
# 6 GB comfortably fits the base RPi OS Lite image (~2 GB) plus packages.
# Raspberry Pi OS first-boot expands the root filesystem to fill the full
# SD card automatically, so we do NOT need to match the card size here.
truncate -s "${IMAGE_SIZE}" "${WORK_IMAGE}"
# Resize the root partition to fill the new space using parted and resize2fs
LOOP_DEV="$(losetup --show -fP "${WORK_IMAGE}")"
log "Attached loop device: ${LOOP_DEV}"
# Partition 2 is the root filesystem on a standard RPi OS image
kpartx -a "${LOOP_DEV}"
sleep 1  # give udev time to create device nodes
# Grow the partition table entry and filesystem
parted -s "${LOOP_DEV}" resizepart 2 100%
# Refresh kpartx device-mapper entries so they reflect the enlarged partition;
# without this, resize2fs sees the old device size and does nothing.
kpartx -u "${LOOP_DEV}"
sleep 1
e2fsck -f -y "/dev/mapper/$(basename "${LOOP_DEV}")p2" || true
resize2fs "/dev/mapper/$(basename "${LOOP_DEV}")p2"
log "Working image resized to ${IMAGE_SIZE}"

# ---------------------------------------------------------------------------
# Step 3 — Mount the image
# ---------------------------------------------------------------------------
log "Step 3: Mounting working image..."
mkdir -p "${MOUNT_DIR}"
mount "/dev/mapper/$(basename "${LOOP_DEV}")p2" "${MOUNT_DIR}"

# RPi OS Bookworm and later (including Trixie) mount the FAT32 boot partition
# at /boot/firmware; older releases use /boot directly.  Detect the correct
# path from the root filesystem so the Ansible tasks use the right paths.
if [ -d "${MOUNT_DIR}/boot/firmware" ]; then
    BOOT_MOUNT_DIR="${MOUNT_DIR}/boot/firmware"
    log "Detected modern layout: mounting boot partition at /boot/firmware"
else
    BOOT_MOUNT_DIR="${MOUNT_DIR}/boot"
    log "Detected legacy layout: mounting boot partition at /boot"
fi
mount "/dev/mapper/$(basename "${LOOP_DEV}")p1" "${BOOT_MOUNT_DIR}"

# ---------------------------------------------------------------------------
# Step 4 — Provision with Ansible (native ARM64 chroot, no QEMU needed)
# ---------------------------------------------------------------------------
log "Step 4: Provisioning image with Ansible (native ARM64 chroot)..."

# Copy the repo into the image so the playbook has access to all templates.
# Must NOT overlap with /opt/hearth — the admin role deploys the backend there
# and the cleanup rm -rf below would otherwise wipe it from the final image.
CHROOT_REPO="/root/hearth-provisioner"
mkdir -p "${MOUNT_DIR}${CHROOT_REPO}"
rsync -a --exclude='.git' --exclude='image/' \
    "${REPO_ROOT}/" "${MOUNT_DIR}${CHROOT_REPO}/"

# Install Ansible inside the image if not already present
systemd-nspawn -D "${MOUNT_DIR}" \
    /bin/bash -c "
        set -e
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq ansible
    "

# Run the playbook targeting localhost inside the chroot
systemd-nspawn -D "${MOUNT_DIR}" \
    /bin/bash -c "
        set -e
        cd ${CHROOT_REPO}
        ansible-playbook \
            -i 'localhost,' \
            -c local \
            --extra-vars @hearth.yaml \
            ansible/site.yml
    "

# Remove the repo copy from the final image
rm -rf "${MOUNT_DIR}${CHROOT_REPO}"

log "Provisioning complete."

# ---------------------------------------------------------------------------
# Step 5 — Validate image configuration (pre-capture checks)
#
# Run static configuration checks inside the nspawn container before
# compressing the image.  Systemd is NOT running here (no --boot), so only
# file-presence and content checks are performed.  A failure here aborts the
# build so misconfigured images are never shipped.
# ---------------------------------------------------------------------------
log "Step 5: Validating image configuration..."

# Write the validation script to a temp file inside the image.
# systemd-nspawn allocates a PTY by default and does not connect stdin from
# the calling process, so a heredoc passed via stdin hangs indefinitely.
# Writing to a file and executing it directly avoids that entirely.
# NOTE: /tmp must NOT be used here — systemd-nspawn mounts a fresh tmpfs
# over /tmp inside the container, wiping anything written there from the host.
VALIDATE_SCRIPT="${MOUNT_DIR}/root/hearth-validate.sh"

# Extract usb_ssh.enabled so the validation script can skip USB OTG checks
# when the feature is disabled. The repo is removed from the image before
# validation runs, so we pass the value in as a hardcoded variable.
USB_SSH_ENABLED="$(python3 - "${HEARTH_CONFIG}" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)
print("true" if cfg.get("usb_ssh", {}).get("enabled", False) else "false")
PYEOF
)"

{
printf '#!/bin/sh\nUSB_SSH_ENABLED=%s\n' "${USB_SSH_ENABLED}"
cat << 'DIAG_EOF'
set +e  # accumulate all failures; exit 1 at the end if any failed
FAIL=0

ok()   { printf '  [OK]   %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1" >&2; }
fail() { printf '  [FAIL] %s\n' "$1" >&2; FAIL=$((FAIL + 1)); }

echo "=== Hearth pre-capture configuration check ==="

echo ""
echo "--- WiFi access point ---"

# hostapd configuration file
[ -f /etc/hostapd/hostapd.conf ] \
    && ok "hostapd.conf present" \
    || fail "hostapd.conf MISSING at /etc/hostapd/hostapd.conf"

# DAEMON_CONF must point to the config file or hostapd starts without it
if grep -qE "^DAEMON_CONF=" /etc/default/hostapd 2>/dev/null; then
    ok "DAEMON_CONF set in /etc/default/hostapd"
else
    fail "DAEMON_CONF not set in /etc/default/hostapd (hostapd will ignore the config)"
fi

# hostapd must be enabled (symlink in multi-user.target.wants)
[ -L /etc/systemd/system/multi-user.target.wants/hostapd.service ] \
    && ok "hostapd.service enabled" \
    || fail "hostapd.service NOT enabled (no symlink in multi-user.target.wants)"

# hostapd drop-in: waits for WiFi netdev and runs rfkill unblock
[ -f /etc/systemd/system/hostapd.service.d/hearth-wlan-wait.conf ] \
    && ok "hostapd drop-in present" \
    || fail "hostapd drop-in MISSING at hostapd.service.d/hearth-wlan-wait.conf"

# dnsmasq configuration file
[ -f /etc/dnsmasq.d/hearth.conf ] \
    && ok "dnsmasq hearth.conf present" \
    || fail "dnsmasq hearth.conf MISSING at /etc/dnsmasq.d/hearth.conf"

# dnsmasq must be enabled
[ -L /etc/systemd/system/multi-user.target.wants/dnsmasq.service ] \
    && ok "dnsmasq.service enabled" \
    || fail "dnsmasq.service NOT enabled (no symlink in multi-user.target.wants)"

# dnsmasq drop-in: waits for hostapd and assigns the AP IP
[ -f /etc/systemd/system/dnsmasq.service.d/hearth-wlan-wait.conf ] \
    && ok "dnsmasq drop-in present" \
    || fail "dnsmasq drop-in MISSING at dnsmasq.service.d/hearth-wlan-wait.conf"

# cfg80211.ieee80211_regdom in cmdline.txt — primary regulatory domain mechanism
# on RPi OS Trixie (raspberrypi-sys-mods firstboot no longer reads wpa_supplicant.conf)
FOUND_CMDLINE_REGDOM=0
for f in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
    if [ -f "$f" ]; then
        if grep -q "cfg80211.ieee80211_regdom=" "$f"; then
            ok "cfg80211.ieee80211_regdom= found in $f"
        else
            fail "cfg80211.ieee80211_regdom= NOT found in $f (WiFi regulatory domain not set — BCM43430 AP will not broadcast)"
        fi
        FOUND_CMDLINE_REGDOM=1
        break
    fi
done
[ "$FOUND_CMDLINE_REGDOM" -eq 1 ] || fail "No cmdline.txt found — cannot verify regulatory domain kernel parameter"

# country code in wpa_supplicant.conf — legacy fallback for older RPi OS images
if grep -qE "^country=" /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null; then
    ok "country= set in wpa_supplicant.conf (legacy fallback present)"
else
    warn "country= NOT set in wpa_supplicant.conf — OK on Trixie (cmdline.txt is the primary mechanism)"
fi

# NetworkManager must not manage the AP interface
if [ -f /etc/NetworkManager/conf.d/hearth-wifi.conf ]; then
    ok "NetworkManager unmanaged config present"
else
    warn "NetworkManager unmanaged config not found — OK if NM is not installed"
fi

echo ""
echo "--- USB OTG SSH ---"

if [ "${USB_SSH_ENABLED}" = "true" ]; then
    # dtoverlay=dwc2 in boot config.txt enables the USB gadget controller
    FOUND_BOOT_CFG=0
    for f in /boot/firmware/config.txt /boot/config.txt; do
        if [ -f "$f" ]; then
            FOUND_BOOT_CFG=1
            if grep -qE "^dtoverlay=dwc2" "$f"; then
                ok "dtoverlay=dwc2 found in $f"
            else
                fail "dtoverlay=dwc2 NOT found in $f (USB OTG SSH will not work)"
            fi
            break
        fi
    done
    [ "$FOUND_BOOT_CFG" -eq 1 ] || fail "No boot config.txt found at /boot/firmware/config.txt or /boot/config.txt"

    # modules-load=dwc2,g_ether in cmdline.txt loads the gadget at boot
    FOUND_CMDLINE=0
    for f in /boot/firmware/cmdline.txt /boot/cmdline.txt; do
        if [ -f "$f" ]; then
            FOUND_CMDLINE=1
            if grep -q "modules-load=dwc2,g_ether" "$f"; then
                ok "modules-load=dwc2,g_ether found in $f"
            else
                fail "modules-load=dwc2,g_ether NOT found in $f (USB gadget module will not load)"
            fi
            break
        fi
    done
    [ "$FOUND_CMDLINE" -eq 1 ] || fail "No boot cmdline.txt found at /boot/firmware/cmdline.txt or /boot/cmdline.txt"
else
    ok "USB OTG SSH disabled — skipping checks"
fi

echo ""
if [ "$FAIL" -ne 0 ]; then
    echo "[FAIL] Pre-capture check FAILED — correct the errors above before flashing."
    exit 1
fi
echo "[OK] All pre-capture checks passed."
DIAG_EOF
} > "${VALIDATE_SCRIPT}"
chmod +x "${VALIDATE_SCRIPT}"
systemd-nspawn -D "${MOUNT_DIR}" /root/hearth-validate.sh
rm -f "${VALIDATE_SCRIPT}"

# ---------------------------------------------------------------------------
# Step 6 — Unmount and compress
# ---------------------------------------------------------------------------
log "Step 6: Unmounting image..."
umount "${BOOT_MOUNT_DIR}"
umount "${MOUNT_DIR}"
kpartx -d "${LOOP_DEV}"
losetup -d "${LOOP_DEV}"
LOOP_DEV=""

log "Step 7: Compressing to ${OUTPUT_IMAGE}..."
mkdir -p "$(dirname "${OUTPUT_IMAGE}")"
xz -T0 -c "${WORK_IMAGE}" > "${OUTPUT_IMAGE}"

COMPRESSED_SIZE="$(du -sh "${OUTPUT_IMAGE}" | cut -f1)"
log "Done. Output: ${OUTPUT_IMAGE} (${COMPRESSED_SIZE})"
log ""
log "Flash with Raspberry Pi Imager (recommended) or dd:"
log "  xzcat ${OUTPUT_IMAGE} | sudo dd of=/dev/sdX bs=4M status=progress"
log "  (replace /dev/sdX with your SD card device)"
log ""
log "Minimum SD card size: ${IMAGE_SIZE} (the root filesystem is automatically"
log "expanded to fill the full card on first boot — no manual resize needed)."
