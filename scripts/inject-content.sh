#!/usr/bin/env bash
# scripts/inject-content.sh — Copy local ZIM and music files onto a Hearth
# SD card via its block device.
#
# Usage:
#   sudo scripts/inject-content.sh <device>
#
# Examples:
#   sudo scripts/inject-content.sh /dev/sdb
#   sudo scripts/inject-content.sh /dev/mmcblk0
#
# To find your device: lsblk
#
# What this does:
#   1. Mounts the card's root partition (partition 2) to a temp directory.
#   2. Copies *.zim files from zims/  →  /srv/hearth/kiwix/
#   3. Copies files from music/       →  /srv/hearth/music/  (subdirs preserved)
#   4. Syncs and unmounts.
#
# Files already present on the card are skipped.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIM_SRC="${REPO_ROOT}/zims"
MUSIC_SRC="${REPO_ROOT}/music"
SCRIPT_NAME="$(basename "$0")"
MOUNT_DIR=""

log() { echo "[${SCRIPT_NAME}] $*"; }
die() { echo "[${SCRIPT_NAME}] ERROR: $*" >&2; exit 1; }

_cleanup() {
    if [ -n "${MOUNT_DIR}" ] && mountpoint -q "${MOUNT_DIR}" 2>/dev/null; then
        umount "${MOUNT_DIR}" 2>/dev/null || true
    fi
    [ -n "${MOUNT_DIR}" ] && rmdir "${MOUNT_DIR}" 2>/dev/null || true
}
trap _cleanup EXIT

[ $# -eq 1 ] || die "Usage: sudo $0 <device>  (e.g. /dev/sdb or /dev/mmcblk0)"
DEVICE="$1"
[ "$(id -u)" -eq 0 ] || die "Must be run as root.  Try: sudo $0 ${DEVICE}"
[ -b "${DEVICE}" ]    || die "Not a block device: ${DEVICE}  (run lsblk to find your card)"

# Partition 2 is the root filesystem on all Raspberry Pi OS images.
# mmcblkX devices use a 'p' separator before the partition number.
if [[ "${DEVICE}" =~ mmcblk[0-9]+$ ]]; then
    ROOT_PART="${DEVICE}p2"
else
    ROOT_PART="${DEVICE}2"
fi
[ -b "${ROOT_PART}" ] || die "Root partition not found: ${ROOT_PART} — is the card fully written?"

MOUNT_DIR="$(mktemp -d /tmp/hearth-inject.XXXXXX)"
log "Mounting ${ROOT_PART}..."
mount "${ROOT_PART}" "${MOUNT_DIR}"

CARD_ROOT="${MOUNT_DIR}"

# ---------------------------------------------------------------------------
# ZIM files → /srv/hearth/kiwix/
# ---------------------------------------------------------------------------

ZIM_DEST="${CARD_ROOT}/srv/hearth/kiwix"

if [ -d "${ZIM_SRC}" ] && ls "${ZIM_SRC}"/*.zim &>/dev/null; then
    [ -d "${ZIM_DEST}" ] || die "/srv/hearth/kiwix not found on card — is this a Hearth image?"
    log "Copying ZIM files to /srv/hearth/kiwix/..."
    for src in "${ZIM_SRC}"/*.zim; do
        name="$(basename "${src}")"
        dst="${ZIM_DEST}/${name}"
        if [ -f "${dst}" ]; then
            log "  ${name} — already present, skipping"
            continue
        fi
        log "  ${name}"
        cp "${src}" "${dst}"
        chmod 644 "${dst}"
    done
else
    log "No ZIM files in zims/ — skipping."
fi

# ---------------------------------------------------------------------------
# Music files → /srv/hearth/music/
# ---------------------------------------------------------------------------

MUSIC_DEST="${CARD_ROOT}/srv/hearth/music"

if [ -d "${MUSIC_SRC}" ] && [ -n "$(ls -A "${MUSIC_SRC}" 2>/dev/null)" ]; then
    [ -d "${MUSIC_DEST}" ] || die "/srv/hearth/music not found on card — is this a Hearth image?"
    log "Copying music files to /srv/hearth/music/..."
    find "${MUSIC_SRC}" -type f | while IFS= read -r src; do
        rel="${src#"${MUSIC_SRC}/"}"
        dst="${MUSIC_DEST}/${rel}"
        if [ -f "${dst}" ]; then
            log "  ${rel} — already present, skipping"
            continue
        fi
        mkdir -p "$(dirname "${dst}")"
        log "  ${rel}"
        cp "${src}" "${dst}"
        chmod 644 "${dst}"
    done
else
    log "No music files in music/ — skipping."
fi

# ---------------------------------------------------------------------------
log "Syncing..."
sync
umount "${MOUNT_DIR}"
rmdir "${MOUNT_DIR}"
MOUNT_DIR=""
log "Done. You can safely eject the card."
