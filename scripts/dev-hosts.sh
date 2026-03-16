#!/usr/bin/env bash
# scripts/dev-hosts.sh — Add or remove local /etc/hosts entries for CafeBox dev
#
# Usage:
#   sudo scripts/dev-hosts.sh add     # Append *.cafe.box entries (idempotent)
#   sudo scripts/dev-hosts.sh remove  # Remove the entries
#
# The entries map the services that CafeBox exposes under the cafe.box domain
# to 127.0.0.1 so a developer's browser resolves them without a real hotspot.

set -euo pipefail

HOSTS_FILE="/etc/hosts"
MARKER_START="# BEGIN cafebox-dev"
MARKER_END="# END cafebox-dev"

ENTRIES="127.0.0.1 cafe.box
127.0.0.1 element.cafe.box
127.0.0.1 books.cafe.box
127.0.0.1 wiki.cafe.box
127.0.0.1 music.cafe.box
127.0.0.1 admin.cafe.box"

_require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo "ERROR: This script must be run as root (use sudo)." >&2
        exit 1
    fi
}

cmd_add() {
    _require_root
    # Idempotent: do nothing if the marker block already exists
    if grep -qF "$MARKER_START" "$HOSTS_FILE"; then
        echo "cafebox-dev entries already present in $HOSTS_FILE — nothing to do."
        return 0
    fi
    # Ensure the file ends with a newline before appending
    if [ -s "$HOSTS_FILE" ] && [ "$(tail -c1 "$HOSTS_FILE" | wc -l)" -eq 0 ]; then
        echo "" >> "$HOSTS_FILE"
    fi
    printf '%s\n%s\n%s\n' "$MARKER_START" "$ENTRIES" "$MARKER_END" >> "$HOSTS_FILE"
    echo "cafebox-dev entries added to $HOSTS_FILE."
}

cmd_remove() {
    _require_root
    if ! grep -qF "$MARKER_START" "$HOSTS_FILE"; then
        echo "No cafebox-dev entries found in $HOSTS_FILE — nothing to do."
        return 0
    fi
    # Remove the block between (and including) the markers
    sed -i "/$MARKER_START/,/$MARKER_END/d" "$HOSTS_FILE"
    echo "cafebox-dev entries removed from $HOSTS_FILE."
}

case "${1:-}" in
    add)    cmd_add ;;
    remove) cmd_remove ;;
    *)
        echo "Usage: sudo $0 {add|remove}" >&2
        exit 1
        ;;
esac
