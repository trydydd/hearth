#!/usr/bin/env bash
# scripts/inject-content.sh — Download content files (ZIMs and music) and
# copy them onto a freshly-flashed Hearth SD card.
#
# Run this immediately after flashing the image with rpi-imager.
#
# Usage:
#   sudo scripts/inject-content.sh <device>
#   sudo scripts/inject-content.sh --dir <root>   # dev/test: skip mount, write directly
#
# Examples:
#   sudo scripts/inject-content.sh /dev/sdb
#   sudo scripts/inject-content.sh /dev/mmcblk0
#   scripts/inject-content.sh --dir /              # Vagrant dev (no sudo needed)
#   scripts/inject-content.sh --dir /mnt/hearth    # Manually-mounted card root
#
# What this does:
#   1. Reads hearth.yaml for enabled ZIM files (name + download URL).
#   2. Reads hearth.yaml for enabled music files (name + download URL).
#   3. Downloads any missing files to local caches (zims/ and music/).
#   4. Mounts the SD card root partition (partition 2).      [skipped with --dir]
#   5. Copies ZIM files into /srv/hearth/kiwix/ on the card.
#   6. Copies music files into /srv/hearth/music/ on the card.
#   7. Sets correct ownership and permissions.
#   8. Unmounts cleanly and syncs.                          [skipped with --dir]
#
# The local zims/ and music/ directories act as persistent caches —
# re-flashing the same content configuration skips all downloads.
#
# Requirements: python3 (with PyYAML), curl, standard Linux mount utilities.
# Requires root when using a block device; --dir mode can run without sudo.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HEARTH_CONFIG="${HEARTH_CONFIG:-${REPO_ROOT}/hearth.yaml}"
ZIM_CACHE="${REPO_ROOT}/zims"
MUSIC_CACHE="${REPO_ROOT}/music"
KIWIX_STORAGE="/srv/hearth/kiwix"
MUSIC_STORAGE="/srv/hearth/music"
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
TARGET_ROOT=""

case "${1:-}" in
    --dir)
        [ $# -eq 2 ] || die "Usage: $0 --dir <root>"
        DIR_MODE=1
        TARGET_ROOT="$2"
        [ -d "${TARGET_ROOT}" ] || die "Directory not found: ${TARGET_ROOT}"
        ;;
    "")
        die "Usage: sudo $0 <device>  (e.g. /dev/sdb or /dev/mmcblk0)
       $0 --dir <root>      (dev/test mode — no mount, e.g. /)"
        ;;
    *)
        [ $# -eq 1 ] || die "Usage: sudo $0 <device>"
        DEVICE="$1"
        [ "$(id -u)" -eq 0 ] || die "Must be run as root.  Try: sudo $0 ${DEVICE}"
        [ -b "${DEVICE}" ]    || die "Not a block device: ${DEVICE}"
        ;;
esac

[ -f "${HEARTH_CONFIG}" ] || die "hearth.yaml not found at ${HEARTH_CONFIG}"

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
# Read ZIM list from hearth.yaml
# ---------------------------------------------------------------------------

log "Reading ZIM configuration from ${HEARTH_CONFIG}..."

ZIM_LINES="$(python3 - "${HEARTH_CONFIG}" <<'PYEOF'
import sys, yaml

with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)

kiwix = cfg.get("services", {}).get("kiwix", {})

if not kiwix.get("enabled", False):
    sys.exit(0)

zims = kiwix.get("content", [])
enabled = [z for z in zims if z.get("enabled", True)]

for z in enabled:
    print(f"{z['name']}\t{z['url']}")
PYEOF
)"

ZIM_NAMES=()
ZIM_URLS=()
if [ -n "${ZIM_LINES}" ]; then
    while IFS=$'\t' read -r name url; do
        ZIM_NAMES+=("${name}")
        ZIM_URLS+=("${url}")
    done <<< "${ZIM_LINES}"
fi

# ---------------------------------------------------------------------------
# Read music list from hearth.yaml
# ---------------------------------------------------------------------------

log "Reading music configuration from ${HEARTH_CONFIG}..."

MUSIC_LINES="$(python3 - "${HEARTH_CONFIG}" <<'PYEOF'
import sys, yaml

with open(sys.argv[1]) as f:
    cfg = yaml.safe_load(f)

music = cfg.get("services", {}).get("music", {})

if not music.get("enabled", False):
    sys.exit(0)

tracks = music.get("content", [])
enabled = [t for t in tracks if t.get("enabled", True)]

for t in enabled:
    print(f"{t['name']}\t{t['url']}")
PYEOF
)"

MUSIC_NAMES=()
MUSIC_URLS=()
if [ -n "${MUSIC_LINES}" ]; then
    while IFS=$'\t' read -r name url; do
        MUSIC_NAMES+=("${name}")
        MUSIC_URLS+=("${url}")
    done <<< "${MUSIC_LINES}"
fi

# ---------------------------------------------------------------------------
# Check we have something to do
# ---------------------------------------------------------------------------

if [ "${#ZIM_NAMES[@]}" -eq 0 ] && [ "${#MUSIC_NAMES[@]}" -eq 0 ]; then
    log "No content configured — nothing to inject."
    exit 0
fi

if [ "${#ZIM_NAMES[@]}" -gt 0 ]; then
    log "Found ${#ZIM_NAMES[@]} ZIM file(s) to inject:"
    for name in "${ZIM_NAMES[@]}"; do
        log "  • ${name}"
    done
fi

if [ "${#MUSIC_NAMES[@]}" -gt 0 ]; then
    log "Found ${#MUSIC_NAMES[@]} music file(s) to inject:"
    for name in "${MUSIC_NAMES[@]}"; do
        log "  • ${name}"
    done
fi

# ---------------------------------------------------------------------------
# Download missing ZIMs to local cache
# ---------------------------------------------------------------------------

if [ "${#ZIM_NAMES[@]}" -gt 0 ]; then
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
fi

# ---------------------------------------------------------------------------
# Download missing music files to local cache
# ---------------------------------------------------------------------------

if [ "${#MUSIC_NAMES[@]}" -gt 0 ]; then
    mkdir -p "${MUSIC_CACHE}"

    for i in "${!MUSIC_NAMES[@]}"; do
        name="${MUSIC_NAMES[$i]}"
        url="${MUSIC_URLS[$i]}"
        dest="${MUSIC_CACHE}/${name}"
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
fi

# ---------------------------------------------------------------------------
# Mount the SD card root partition (skipped in --dir mode)
# ---------------------------------------------------------------------------

FS_ROOT=""
if [ "${DIR_MODE}" -eq 1 ]; then
    # Strip trailing slash so path joins below are consistent.
    FS_ROOT="${TARGET_ROOT%/}"
    log "Dir mode: filesystem root at ${FS_ROOT:-/}"
else
    MOUNT_DIR="$(mktemp -d /tmp/hearth-inject.XXXXXX)"
    log "Mounting ${ROOT_PART} at ${MOUNT_DIR}..."
    mount "${ROOT_PART}" "${MOUNT_DIR}"
    FS_ROOT="${MOUNT_DIR}"
fi

# ---------------------------------------------------------------------------
# Inject ZIM files into /srv/hearth/kiwix/
# ---------------------------------------------------------------------------

if [ "${#ZIM_NAMES[@]}" -gt 0 ]; then
    KIWIX_DEST="${FS_ROOT}${KIWIX_STORAGE}"

    if [ ! -d "${KIWIX_DEST}" ]; then
        die "Kiwix storage directory not found: ${KIWIX_STORAGE}
Is this a Hearth image? Was kiwix enabled in hearth.yaml at build time?"
    fi

    # Resolve kiwix UID/GID from the card's own /etc/passwd — avoids hardcoding.
    KIWIX_UID="$(grep "^kiwix:" "${FS_ROOT}/etc/passwd" 2>/dev/null | cut -d: -f3)" || true
    KIWIX_GID="$(grep "^kiwix:" "${FS_ROOT}/etc/group"  2>/dev/null | cut -d: -f3)" || true
    KIWIX_UID="${KIWIX_UID:-$(stat -c '%u' "${KIWIX_DEST}")}"
    KIWIX_GID="${KIWIX_GID:-$(stat -c '%g' "${KIWIX_DEST}")}"

    log "Injecting ZIM files into ${KIWIX_STORAGE}..."
    for name in "${ZIM_NAMES[@]}"; do
        src="${ZIM_CACHE}/${name}"
        dst="${KIWIX_DEST}/${name}"

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
fi

# ---------------------------------------------------------------------------
# Inject music files into /srv/hearth/music/
# ---------------------------------------------------------------------------

if [ "${#MUSIC_NAMES[@]}" -gt 0 ]; then
    MUSIC_DEST="${FS_ROOT}${MUSIC_STORAGE}"

    if [ ! -d "${MUSIC_DEST}" ]; then
        die "Music storage directory not found: ${MUSIC_STORAGE}
Is this a Hearth image? Was music enabled in hearth.yaml at build time?"
    fi

    # Resolve hearth-jukebox UID/GID from the card's own /etc/passwd.
    JUKEBOX_UID="$(grep "^hearth-jukebox:" "${FS_ROOT}/etc/passwd" 2>/dev/null | cut -d: -f3)" || true
    JUKEBOX_GID="$(grep "^hearth-jukebox:" "${FS_ROOT}/etc/group"  2>/dev/null | cut -d: -f3)" || true
    JUKEBOX_UID="${JUKEBOX_UID:-$(stat -c '%u' "${MUSIC_DEST}")}"
    JUKEBOX_GID="${JUKEBOX_GID:-$(stat -c '%g' "${MUSIC_DEST}")}"

    log "Injecting music files into ${MUSIC_STORAGE}..."
    for name in "${MUSIC_NAMES[@]}"; do
        src="${MUSIC_CACHE}/${name}"
        dst="${MUSIC_DEST}/${name}"

        if [ -f "${dst}" ]; then
            log "Already present: ${name} — skipping."
            continue
        fi

        log "Copying ${name}..."
        cp "${src}" "${dst}"
        chown "${JUKEBOX_UID}:${JUKEBOX_GID}" "${dst}"
        chmod 644 "${dst}"
        log "  Done."
    done
fi

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
    log "Done. Content is on the card."
    log "Services will index new content automatically on first boot."
else
    log ""
    log "Done. Restart services to pick up injected content:"
    log "  sudo systemctl restart kiwix          # for new ZIM files"
    log "  sudo systemctl restart hearth-jukebox # for new music files"
fi
