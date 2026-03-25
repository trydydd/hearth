#!/bin/bash
# volume-setup.sh — Hearth chat ephemeral encrypted volume setup.
#
# Run at boot by hearth-volume.service. Creates a dm-crypt plain-mode device
# backed by a sparse file, formats it as ext4, and mounts it. The encryption
# key is generated from /dev/urandom and piped directly to cryptsetup — it is
# never written to disk. When the box powers off the key is gone and the
# volume contents are permanently unrecoverable.
#
# Safe to run after an unclean shutdown: stale mounts and device mappings are
# cleaned up unconditionally before setup begins.

set -euo pipefail

BACKING="/srv/cafebox/chat.img"
MAPPING="chat-volume"
MOUNT="/srv/cafebox/chat-data"
USER="hearth-chat"

# ---- Clean up any stale state from an unclean shutdown --------------------

if mountpoint -q "$MOUNT" 2>/dev/null; then
    umount "$MOUNT"
fi

if [ -e /dev/mapper/"$MAPPING" ]; then
    cryptsetup close "$MAPPING"
fi

# ---- Open dm-crypt plain device with an ephemeral random key --------------
# Key is piped directly from openssl — never touches disk.

openssl rand 32 | cryptsetup open \
    --type plain \
    --cipher aes-cbc-essiv:sha256 \
    --key-size 256 \
    --key-file - \
    "$BACKING" "$MAPPING"

# ---- Format (always — contents are intentionally ephemeral) ---------------

mkfs.ext4 -q /dev/mapper/"$MAPPING"

# ---- Mount ----------------------------------------------------------------

mkdir -p "$MOUNT"
mount /dev/mapper/"$MAPPING" "$MOUNT"

# Set ownership so the chat server can write its SQLite database
chown "$USER":"$USER" "$MOUNT"
chmod 750 "$MOUNT"
