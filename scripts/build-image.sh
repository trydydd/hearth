#!/usr/bin/env bash
# scripts/build-image.sh — Build a flashable CafeBox Raspberry Pi image
#
# Usage:
#   scripts/build-image.sh [--output <path>] [--work-dir <path>]
#
# Environment variables (override defaults):
#   CAFE_CONFIG   Path to cafe.yaml                (default: cafe.yaml)
#   OUTPUT_IMAGE  Destination .img.xz file         (default: image/cafebox.img.xz)
#   WORK_DIR      Scratch directory for build artifacts (default: /tmp/cafebox-build)
#   RPI_OS_URL    URL of the base Raspberry Pi OS Lite image
#   KEEP_WORK     Set to "1" to keep WORK_DIR after a successful build
#
# What this script does:
#   1. Downloads the latest Raspberry Pi OS Lite (64-bit) image.
#   2. Copies it to a raw working image so the original is never modified.
#   3. Mounts the image via a loop device and runs ansible/site.yml inside
#      a chroot, provisioning the image exactly as the Vagrantfile Ansible
#      provisioner would.
#   4. Compresses the finished image to <output>.img.xz.
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
CAFE_CONFIG="${CAFE_CONFIG:-${REPO_ROOT}/cafe.yaml}"
OUTPUT_IMAGE="${OUTPUT_IMAGE:-${REPO_ROOT}/image/cafebox.img.xz}"
WORK_DIR="${WORK_DIR:-/tmp/cafebox-build}"
KEEP_WORK="${KEEP_WORK:-0}"

# Raspberry Pi OS Lite 64-bit (Bookworm) — update URL for newer releases
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
    # Unmount in reverse order; ignore errors during cleanup
    if mountpoint -q "${MOUNT_DIR}/boot" 2>/dev/null; then
        umount "${MOUNT_DIR}/boot" 2>/dev/null || true
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

[ -f "${CAFE_CONFIG}" ] || die "cafe.yaml not found at ${CAFE_CONFIG}"

OUTPUT_DIR="$(dirname "${OUTPUT_IMAGE}")"
mkdir -p "${OUTPUT_DIR}" "${WORK_DIR}"

# Derived paths
RAW_IMAGE="${WORK_DIR}/raspios-lite.img"
WORK_IMAGE="${WORK_DIR}/cafebox-work.img"
MOUNT_DIR="${WORK_DIR}/mnt"
LOOP_DEV=""

trap _cleanup EXIT

log "Build started"
log "  Host   : ${HOST_ARCH} (native — no emulation)"
log "  Config : ${CAFE_CONFIG}"
log "  Output : ${OUTPUT_IMAGE}"
log "  WorkDir: ${WORK_DIR}"

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
# Extend partition/filesystem to give headroom for provisioned packages
# (Raspberry Pi OS images are typically ~2 GB; we grow to 12 GB)
truncate -s 12G "${WORK_IMAGE}"
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
log "Working image resized to 12 GB"

# ---------------------------------------------------------------------------
# Step 3 — Mount the image
# ---------------------------------------------------------------------------
log "Step 3: Mounting working image..."
mkdir -p "${MOUNT_DIR}"
mount "/dev/mapper/$(basename "${LOOP_DEV}")p2" "${MOUNT_DIR}"
mount "/dev/mapper/$(basename "${LOOP_DEV}")p1" "${MOUNT_DIR}/boot"

# ---------------------------------------------------------------------------
# Step 4 — Provision with Ansible (native ARM64 chroot, no QEMU needed)
# ---------------------------------------------------------------------------
log "Step 4: Provisioning image with Ansible (native ARM64 chroot)..."

# Copy the repo into the image so the playbook has access to all templates
CHROOT_REPO="/opt/cafe-box"
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
            --extra-vars @cafe.yaml \
            ansible/site.yml
    "

# Remove the repo copy from the final image
rm -rf "${MOUNT_DIR}${CHROOT_REPO}"

log "Provisioning complete."

# ---------------------------------------------------------------------------
# Step 5 — Unmount and compress
# ---------------------------------------------------------------------------
log "Step 5: Unmounting image..."
umount "${MOUNT_DIR}/boot"
umount "${MOUNT_DIR}"
kpartx -d "${LOOP_DEV}"
losetup -d "${LOOP_DEV}"
LOOP_DEV=""

log "Step 6: Compressing to ${OUTPUT_IMAGE}..."
mkdir -p "$(dirname "${OUTPUT_IMAGE}")"
xz -T0 -c "${WORK_IMAGE}" > "${OUTPUT_IMAGE}"

COMPRESSED_SIZE="$(du -sh "${OUTPUT_IMAGE}" | cut -f1)"
log "Done. Output: ${OUTPUT_IMAGE} (${COMPRESSED_SIZE})"
log ""
log "Flash with:"
log "  xzcat ${OUTPUT_IMAGE} | sudo dd of=/dev/sdX bs=4M status=progress"
log "  (replace /dev/sdX with your SD card device)"
