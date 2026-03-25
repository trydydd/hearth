#!/usr/bin/env bash
# scripts/inject-zims.sh — Download ZIM content files and copy them onto a
# freshly-flashed CafeBox SD card.
#
# Run this immediately after flashing the image with rpi-imager.
#
# Usage:
#   sudo scripts/inject-zims.sh <device>
#   sudo scripts/inject-zims.sh --dir <path>   # dev/test: skip mount, write directly
#
# Examples:
#   sudo scripts/inject-zims.sh /dev/sdb
#   sudo scripts/inject-zims.sh /dev/mmcblk0
#   scripts/inject-zims.sh --dir /srv/cafebox/kiwix   # Vagrant dev test (no sudo needed)
#
# What this does:
#   1. Reads cafe.yaml for enabled ZIM files (name + download URL).
#   2. Downloads any missing ZIMs to the local zims/ cache (skips if cached).
#   3. Mounts the SD card root partition (partition 2).      [skipped with --dir]
#   4. Copies ZIM files into /srv/cafebox/kiwix/ on the card.
#   5. Sets correct ownership and permissions.
#   6. Unmounts cleanly and syncs.                          [skipped with --dir]
#
# The local zims/ directory acts as a persistent cache — re-flashing the same
# content configuration skips all downloads.
#
# Requirements: python3 (with PyYAML), curl, standard Linux mount utilities.
# Requires root when using a block device; --dir mode can run without sudo.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CAFE_CONFIG="${CAFE_CONFIG:-${REPO_ROOT}/cafe.yaml}"
ZIM_CACHE="${REPO_ROOT}/zims"
KIWIX_STORAGE="/srv/cafebox/kiwix"
SCRIPT_NAME="$(basename "$0")"
LOG_PREFIX="[${SCRIPT_NAME}]"
MOUNT_DIR=""

log()  { echo "${LOG_PREFIX} $*"; }
die()  { echo "${LOG_PREFIX} ERROR: $*" >&2; exit 1; }

_cleanup() {
    if [ -n "${MOUNT_DIR}" ] && mountpoint -q "${MOUNT_DIR}" 2>/dev/null; then
        log "Unmounting ${MOUNT_DIR}..."
        umount "${MOUNT_DIR}" 2>/dev/null || true
    fi
    if [ -n "${MOUNT_DIR}" ] && [ -d "${MOUNT_DIR}" ]; then
        rmdir "${MOUNT_DIR}" 2>/dev/null || true
    fi
}

trap _cleanup EXIT

# ---------------------------------------------------------------------------
# Arguments and pre-flight
# ---------------------------------------------------------------------------

DIR_MODE=0
DEVICE=""
TARGET_DIR=""

case "${1:-}" in
    --dir)
        [ $# -eq 2 ] || die "Usage: $0 --dir <path>"
        DIR_MODE=1
        TARGET_DIR="$2"
        [ -d "${TARGET_DIR}" ] || die "Directory not found: ${TARGET_DIR}"
        ;;
    "")
        die "Usage: sudo $0 <device>  (e.g. /dev/sdb or /dev/mmcblk0)
       $0 --dir <path>      (dev/test mode — no mount)"
        ;;
    *)
        [ $# -eq 1 ] || die "Usage: sudo $0 <device>"
        DEVICE="$1"
        [ "$(id -u)" -eq 0 ] || die "Must be run as root.  Try: sudo $0 ${DEVICE}"
        [ -b "${DEVICE}" ]    || die "Not a block device: ${DEVICE}"
        ;;
esac

[ -f "${CAFE_CONFIG}" ] || die "cafe.yaml not found at ${CAFE_CONFIG}"

command -v python3 >/dev/null 2>&1 || die "python3 is required but not found."
command -v curl    >/dev/null 2>&1 || die "curl is required but not found."
python3 -c "import yaml" 2>/dev/null || die "PyYAML is required: pip install pyyaml"

# ---------------------------------------------------------------------------
# Derive root partition path (block device mode only)
# Handles both /dev/sdX (→ /dev/sdX2) and /dev/mmcblkX (→ /dev/mmcblkXp2)
# ---------------------------------------------------------------------------

ROOT_PART=""
if [ "${DIR_MODE}" -eq 0 ]; then
    if [[ "${DEVICE}" =~ mmcblk[0-9]+$ ]]; then
        ROOT_PART="${DEVICE}p2"
    else
        ROOT_PART="${DEVICE}2"
    fi
    [ -b "${ROOT_PART}" ] || \
        die "Root partition not found: ${ROOT_PART}. Is the card fully written?"
fi

# ---------------------------------------------------------------------------
# Read ZIM list from cafe.yaml
# ---------------------------------------------------------------------------

log "Reading ZIM configuration from ${CAFE_CONFIG}..."

ZIM_LINES="$(python3 - "${CAFE_CONFIG}" <<'PYEOF'
import sys, yaml

with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)

kiwix = cfg.get("services", {}).get("kiwix", {})

if not kiwix.get("enabled", False):
    # kiwix not enabled — nothing to do
    sys.exit(0)

zims = kiwix.get("content", [])
enabled = [z for z in zims if z.get("enabled", True)]

if not enabled:
    print("NO_ZIMS", file=sys.stderr)
    sys.exit(0)

for z in enabled:
    print(f"{z['name']}\t{z['url']}")
PYEOF
)"

if [ -z "${ZIM_LINES}" ]; then
    log "No ZIM files configured or kiwix is disabled — nothing to inject."
    exit 0
fi

# Parse into parallel arrays
ZIM_NAMES=()
ZIM_URLS=()
while IFS=$'\t' read -r name url; do
    ZIM_NAMES+=("${name}")
    ZIM_URLS+=("${url}")
done <<< "${ZIM_LINES}"

log "Found ${#ZIM_NAMES[@]} ZIM file(s) to inject:"
for name in "${ZIM_NAMES[@]}"; do
    log "  • ${name}"
done

# ---------------------------------------------------------------------------
# Download missing ZIMs to local cache
# ---------------------------------------------------------------------------

mkdir -p "${ZIM_CACHE}"

for i in "${!ZIM_NAMES[@]}"; do
    name="${ZIM_NAMES[$i]}"
    url="${ZIM_URLS[$i]}"
    dest="${ZIM_CACHE}/${name}"
    part="${dest}.part"

    if [ -f "${dest}" ]; then
        log "Cached: ${name} — skipping download."
        continue
    fi

    log "Downloading: ${name}"
    log "  From: ${url}"
    rm -f "${part}"
    if ! curl -L --progress-bar -o "${part}" "${url}"; then
        rm -f "${part}"
        die "Download failed: ${name}"
    fi
    mv "${part}" "${dest}"
    log "  Saved to cache: ${dest}"
done

# ---------------------------------------------------------------------------
# Mount the SD card root partition (skipped in --dir mode)
# ---------------------------------------------------------------------------

if [ "${DIR_MODE}" -eq 1 ]; then
    DEST_DIR="${TARGET_DIR}"
    log "Dir mode: writing directly to ${DEST_DIR}"
    KIWIX_UID="$(stat -c '%u' "${DEST_DIR}")"
    KIWIX_GID="$(stat -c '%g' "${DEST_DIR}")"
else
    MOUNT_DIR="$(mktemp -d /tmp/cafebox-inject.XXXXXX)"
    log "Mounting ${ROOT_PART} at ${MOUNT_DIR}..."
    mount "${ROOT_PART}" "${MOUNT_DIR}"

    DEST_DIR="${MOUNT_DIR}${KIWIX_STORAGE}"
    if [ ! -d "${DEST_DIR}" ]; then
        die "Kiwix storage directory not found on card: ${KIWIX_STORAGE}
    Is this a CafeBox image? Was kiwix enabled in cafe.yaml at build time?"
    fi

    # Resolve kiwix UID/GID from the card's own /etc/passwd — avoids hardcoding.
    KIWIX_UID="$(grep "^kiwix:" "${MOUNT_DIR}/etc/passwd" 2>/dev/null | cut -d: -f3)" || true
    KIWIX_GID="$(grep "^kiwix:" "${MOUNT_DIR}/etc/group"  2>/dev/null | cut -d: -f3)" || true
    KIWIX_UID="${KIWIX_UID:-$(stat -c '%u' "${DEST_DIR}")}"
    KIWIX_GID="${KIWIX_GID:-$(stat -c '%g' "${DEST_DIR}")}"
fi

# ---------------------------------------------------------------------------
# Copy ZIMs into the destination
# ---------------------------------------------------------------------------

for name in "${ZIM_NAMES[@]}"; do
    src="${ZIM_CACHE}/${name}"
    dst="${DEST_DIR}/${name}"

    if [ -f "${dst}" ]; then
        log "Already present: ${name} — skipping."
        continue
    fi

    log "Copying ${name}..."
    cp "${src}" "${dst}"
    chown "${KIWIX_UID}:${KIWIX_GID}" "${dst}"
    chmod 644 "${dst}"
    log "  Done."
done

# ---------------------------------------------------------------------------
# Unmount and sync (skipped in --dir mode)
# ---------------------------------------------------------------------------

if [ "${DIR_MODE}" -eq 0 ]; then
    log "Syncing..."
    sync
    log "Unmounting ${ROOT_PART}..."
    umount "${MOUNT_DIR}"
    rmdir "${MOUNT_DIR}"
    MOUNT_DIR=""
    log ""
    log "Done. ZIM files are on the card."
    log "The kiwix service will index them automatically on first boot."
else
    log ""
    log "Done. Restart kiwix to index the new ZIM:"
    log "  sudo systemctl restart kiwix"
fi
