#!/usr/bin/env bash
# scripts/dev-hosts.sh — Add or remove local /etc/hosts entries for Hearth dev
#
# Usage:
#   sudo scripts/dev-hosts.sh add     # Append *.hearth.home entries (idempotent)
#   sudo scripts/dev-hosts.sh remove  # Remove the entries
#
# The entries map the services that Hearth exposes under the hearth.home domain
# to 127.0.0.1 so a developer's browser resolves them without a real hotspot.

set -euo pipefail

HOSTS_FILE="/etc/hosts"
MARKER_START="# BEGIN hearth-dev"
MARKER_END="# END hearth-dev"

ENTRIES="127.0.0.1 hearth.home"

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
        echo "hearth-dev entries already present in $HOSTS_FILE — nothing to do."
        return 0
    fi
    # Ensure the file ends with a newline before appending
    if [ -s "$HOSTS_FILE" ] && [ "$(tail -c1 "$HOSTS_FILE" | wc -l)" -eq 0 ]; then
        echo "" >> "$HOSTS_FILE"
    fi
    printf '%s\n%s\n%s\n' "$MARKER_START" "$ENTRIES" "$MARKER_END" >> "$HOSTS_FILE"
    echo "hearth-dev entries added to $HOSTS_FILE."
}

cmd_remove() {
    _require_root
    if ! grep -qF "$MARKER_START" "$HOSTS_FILE"; then
        echo "No hearth-dev entries found in $HOSTS_FILE — nothing to do."
        return 0
    fi
    # Remove the block between (and including) the markers
    sed -i "/$MARKER_START/,/$MARKER_END/d" "$HOSTS_FILE"
    echo "hearth-dev entries removed from $HOSTS_FILE."
}

case "${1:-}" in
    add)    cmd_add ;;
    remove) cmd_remove ;;
    *)
        echo "Usage: sudo $0 {add|remove}" >&2
        exit 1
        ;;
esac
